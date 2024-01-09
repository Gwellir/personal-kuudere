import logging
from collections import namedtuple
from http import HTTPStatus
from typing import List
from urllib.parse import urlsplit, urlunsplit

import requests
from telegram import InputMediaPhoto, ParseMode

import config
from handler_modules.base import Handler
from handler_modules.twitter_images.parser import parse_tweet
from handler_modules.twitter_images.scraper import scrape_tweet

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
            images = [
                media["media_url_https"]
                for media in tweet_data["attached_media"]
                if media["type"] == "photo"
            ]
            if images:
                return {
                    "url": url,
                    "id": tweet_data.get("id"),
                    "images": images,
                    "name": tweet_data.get("name"),
                    "screen_name": tweet_data.get("screen_name"),
                    "language": tweet_data.get("language"),
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
        posts_with_images = []
        for num, url in enumerate(params):
            raw_tweet = scrape_tweet(url)
            has_img = False
            if raw_tweet:
                parsed_tweet = self._get_tweet_data(raw_tweet, url)
                if parsed_tweet:
                    posts_with_images.append(parsed_tweet)
                    has_img = True
            else:
                semi_parsed_tweet = self._get_fx_data(url)
                if semi_parsed_tweet:
                    posts_with_images.append(semi_parsed_tweet)
                    has_img = True
            if not has_img:
                self.hidden.pop(num)

        return posts_with_images

    def answer(self, result):
        for num, item in enumerate(result):
            caption = (
                'Фото из <a href="{url}">твита</a> {screen_name} ({name})\n'
                '<a href="{original}">&gt; сообщение от {author} &lt;</a> \n\n'
                '{text}'.format(
                    original=self.message.link,
                    author=self.user.full_name,
                    **item,
                )
            )
            # drop the t.co link to the tweet itself
            caption = " ".join(caption.split(" ")[:-1])
            media_group = [
                InputMediaPhoto(
                    image,
                    parse_mode=ParseMode.HTML,
                    # only add the caption to image #0
                    caption=caption if not i else None,
                )
                for i, image in enumerate(item["images"])
            ]
            self.chat.send_media_group(
                media=media_group,
                disable_notification=True,
                api_kwargs={"has_spoiler": True} if self.hidden[num] else None,
            )
