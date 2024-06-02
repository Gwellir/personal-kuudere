import logging
from collections import namedtuple
from http import HTTPStatus
from typing import List
from urllib.parse import urlsplit, urlunsplit

import requests
from strip_tags import strip_tags
from telegram import InputMediaPhoto, ParseMode, InputMediaVideo
from telegram.error import BadRequest

import config
from handler_modules.base import Handler
from handler_modules.image_extractor.models import PostData, MediaType
from handler_modules.image_extractor.twitter.scraper import TwitterScraper
from handler_modules.image_extractor.vk.scraper import VkScraper

logger = logging.getLogger("handler.extract_images")

NormalizedURL = namedtuple("NormalizedURL", ["url", "hidden"])


def _normalize_url(url):
    host: str
    scheme, host, path, query, fragment = urlsplit(url)
    if host.startswith("www."):
        host = host[4:]
    return scheme, host, path, query, fragment


def _check_is_post_link(service: str, path: str):
    if service == "twitter.com":
        return path.find("/status/") >= 0
    elif service == "vk.com":
        return path.find("/wall") >= 0


def select_scraper(url):
    if "twitter.com" in url:
        return TwitterScraper
    elif "vk.com" in url:
        return VkScraper
    else:
        return None


class TwitterExtractor(Handler):
    hosts = {
        "twitter.com": "twitter.com",
        "fxtwitter.com": "twitter.com",
        "vxtwitter.com": "twitter.com",
        "x.com": "twitter.com",
        "vk.com": "vk.com",
        "vk.ru": "vk.com",
        "m.vk.com": "vk.com",
    }

    def __init__(self):
        super().__init__()
        self.hidden: List[bool] = []
        self.normalized_urls: List[str] = []

    def _check_to_hide(self, url):
        if "hide" in set(self.message.text.split()):
            return True
        if f"!{url}" in set(self.message.text.split()):
            return True

    def parse(self, args: list):
        self.hidden = []
        if self.message.edit_date:
            return []
        urls = self.message.parse_entities(types=["url"]).values()
        self.normalized_urls: List[str] = []
        for url in urls:
            scheme, host, path, query, fragment = _normalize_url(url)
            if host in self.hosts and _check_is_post_link(self.hosts[host], path):
                self.hidden.append(self._check_to_hide(url))
                host = self.hosts[host]
                self.normalized_urls.append(
                    urlunsplit((scheme, host, path, None, None))
                )

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
                if (
                    res.status_code == HTTPStatus.OK
                    and res.url != fx_url
                    and res.url != previous_photo_url
                ):
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
                "text": "<i>Could not parse tweet...</i> ...",
            }

    def process(self, params: list):
        posts_with_media = []
        for num, url in enumerate(params):
            Scraper = select_scraper(url)
            post_data = Scraper().scrape(url)
            has_media = False
            if post_data:
                posts_with_media.append(post_data)
                has_media = True
            if not has_media:
                self.hidden.pop(num)

        return posts_with_media

    @staticmethod
    def _form_media_group(item: PostData, caption):
        media_group = []
        for i, media in enumerate(item.attached_media):
            wrapper = (
                InputMediaPhoto if media.type == MediaType.IMAGE else InputMediaVideo
            )
            media_group.append(
                wrapper(
                    media.url,
                    parse_mode=ParseMode.HTML,
                    # only add the caption to image #0
                    caption=caption if not i else None,
                )
            )

        return media_group

    def answer(self, result: list[PostData]):
        for num, item in enumerate(result):
            if not item.attached_media:
                continue
            prefix = (
                'Медиа из <a href="{url}">поста</a> {name}\n'
                '<a href="{original}">&gt; сообщение от {author} &lt;</a>'.format(
                    original=self.message.link,
                    author=self.user.full_name,
                    **item.model_dump(),
                )
            )

            # or shorten the text from vk if it's too long
            if len(strip_tags(item.text)) >= (
                remainder_len := 1024 - len(strip_tags(prefix))
            ):
                item.text = strip_tags(item.text)[: remainder_len - 8] + " &lt;...&gt;"

            caption = "{prefix}\n\n{text}".format(
                prefix=prefix,
                text=item.text,
            )

            media_group = self._form_media_group(item, caption)
            try:
                self.chat.send_media_group(
                    media=media_group,
                    disable_notification=True,
                    api_kwargs={"has_spoiler": True} if self.hidden[num] else None,
                )
            except BadRequest as br:
                if (
                    br.message
                    == 'Failed to send message #1 with the error message "wrong file identifier/http url specified"'
                ):
                    self.chat.send_message(
                        f"<code>Не удалось загрузить медиа...</code>\n\n{caption}",
                        parse_mode=ParseMode.HTML,
                        disable_notification=True,
                    )
