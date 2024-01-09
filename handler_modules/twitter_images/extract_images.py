import logging
from collections import namedtuple
from http import HTTPStatus
from typing import List
from urllib.parse import urlsplit, urlunsplit

import requests
from telegram import InputMediaPhoto, ParseMode, InputMediaVideo

import config
from handler_modules.base import Handler
from handler_modules.twitter_images.parser import parse_tweet
from handler_modules.twitter_images.scraper import vx_scrape_tweet

logger = logging.getLogger("handler.extract_images")

NormalizedURL = namedtuple('NormalizedURL', ['url', 'hidden'])


class TwitterExtractor(Handler):
    hosts = [
        'twitter.com',
        'fxtwitter.com',
        'vxtwitter.com',
        'x.com',
    ]

    def __init__(self):
        super().__init__()
        self.hidden: List[bool] = []
        self.normalized_urls: List[str] = []

    def _check_to_hide(self, url):
        if "hide" in set(self.message.text.split()):
            return True
        if f"!{url}" in set(self.message.text.split()):
            return True

    def _normalize_url(self, url):
        host: str
        scheme, host, path, query, fragment = urlsplit(url)
        if host.startswith("www."):
            host = host[4:]
        return scheme, host, path, query, fragment

    def parse(self, args: list):
        self.hidden = []
        if self.message.edit_date:
            return []
        urls = self.message.parse_entities(types=["url"]).values()
        self.normalized_urls: List[str] = []
        for url in urls:
            scheme, host, path, query, fragment = self._normalize_url(url)
            if host in self.hosts and path.find('/status/') >= 0:
                self.hidden.append(self._check_to_hide(url))
                host = 'twitter.com'
                self.normalized_urls.append(urlunsplit((scheme, host, path, None, None)))

        return self.normalized_urls

    def _resolve_url(self, url):
        while True:
            try:
                res = requests.get(url)
                url = res.url
                break
            except requests.exceptions.MissingSchema:
                url = f"https://{url}"
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ConnectTimeout,
            ):
                break
        return url

    def _get_tweet_data(self, raw_data: dict, url: str):
        tweet_data = parse_tweet(raw_data)
        if tweet_data["attached_media"]:
            # the only video in a tweet works finely on mobile
            if tweet_data["attached_media"][0]["type"] == "video" and len(tweet_data) == 1:
                return None
            media_list = [
                (media["url"], media["type"])
                for media in tweet_data["attached_media"]
                if media["type"] in ("image", "video")
            ]
            if media_list:
                return {
                    "url": url,
                    "id": tweet_data.get("id"),
                    "media": media_list,
                    "name": tweet_data.get("name"),
                    "screen_name": tweet_data.get("screen_name"),
                    "text": tweet_data.get("text"),
                }

    def _get_fx_data(self, url: str):
        name = url.split("/")[3]
        id_ = url.split("/")[5]
        dl_url = url.replace("twitter.com", "dl.fxtwitter.com")
        images = []
        previous_photo_url = ""
        for photo_no in range(1, 5):
            try:
                fx_url = dl_url + "/photo/" + str(photo_no)
                res = requests.get(
                    fx_url,
                    proxies={
                        "https": config.proxy_auth_url,
                        "http": config.proxy_auth_url,
                    },
                )
                if res.status_code == HTTPStatus.OK and res.url != fx_url and res.url != previous_photo_url:
                    previous_photo_url = res.url
                    images.append(res.url)
                else:
                    break
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ConnectTimeout,
            ):
                break

        if images:
            return {
                "url": url,
                "id": id_,
                "images": images,
                "name": name,
                "screen_name": "",
                "text": '<i>Could not parse tweet...</i> ...',
            }

    def process(self, params: list):
        posts_with_media = []
        for num, url in enumerate(params):
            raw_tweet = vx_scrape_tweet(url)
            has_media = False
            if raw_tweet:
                parsed_tweet = self._get_tweet_data(raw_tweet, url)
                if parsed_tweet:
                    posts_with_media.append(parsed_tweet)
                    has_media = True
            if not has_media:
                self.hidden.pop(num)

        return posts_with_media

    @staticmethod
    def _form_media_group(item, caption):
        media_group = []
        for i, media in enumerate(item["media"]):
            wrapper = InputMediaPhoto if media[1] == "image" else InputMediaVideo
            media_group.append(
                wrapper(
                    media[0],
                    parse_mode=ParseMode.HTML,
                    # only add the caption to image #0
                    caption=caption if not i else None,
                )
            )

        return media_group

    def answer(self, result):
        for num, item in enumerate(result):
            caption = (
                'Медиа из <a href="{url}">твита</a> {screen_name} ({name})\n'
                '<a href="{original}">&gt; сообщение от {author} &lt;</a> \n\n'
                '{text}'.format(
                    original=self.message.link,
                    author=self.user.full_name,
                    **item,
                )
            )
            # drop the t.co link to the tweet itself
            caption = " ".join(caption.split(" ")[:-1])
            media_group = self._form_media_group(item, caption)
            self.chat.send_media_group(
                media=media_group,
                disable_notification=True,
                api_kwargs={"has_spoiler": True} if self.hidden[num] else None,
            )
