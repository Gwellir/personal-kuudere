import logging
import tempfile
from collections import namedtuple
from typing import List
from urllib.parse import urlsplit, urlunsplit

import requests
from telegram import InputMediaPhoto, ParseMode, InputMediaVideo
from telegram.error import BadRequest, NetworkError

import config
from handler_modules.base import Handler
from handler_modules.image_extractor.models import PostData, MediaType
from handler_modules.image_extractor.twitter.scraper import TwitterScraper
from handler_modules.image_extractor.vk.scraper import VkScraper

logger = logging.getLogger("handler.extract_images")

NormalizedURL = namedtuple("NormalizedURL", ["url", "hidden"])


twitter_scraper = TwitterScraper()
vk_scraper = VkScraper()


def _normalize_url(url):
    host: str
    scheme, host, path, query, fragment = urlsplit(url)
    if host.startswith("www."):
        host = host[4:]
    return scheme, host, path, query, fragment


def _check_is_post_link(service: str, url: str) -> bool:
    if service == "twitter.com":
        return url.find("/status/") >= 0
    elif service == "vk.com":
        if vk_scraper.pattern.findall(url):
            return True


def select_scraper(url):
    if "twitter.com" in url:
        return twitter_scraper
    elif "vk.com" in url:
        return vk_scraper
    else:
        return None


def get_bytes(file: str | bytes) -> bytes:
    if isinstance(file, bytes):
        return file
    with open(file, "rb") as f:
        return f.read()


def load_media_video_from_url(url: str, caption: str | None) -> InputMediaVideo:
    tmp = tempfile.TemporaryFile("w+b")
    logger.info(f"Saving file {url}...")
    content = requests.get(
        url,
        proxies={
            "https": config.proxy_auth_url,
            "http": config.proxy_auth_url,
        },
    ).content
    tmp.write(content)
    logger.info(f"Saved {len(content)} bytes into temporary file")
    tmp.seek(0)
    result_media = InputMediaVideo(
        tmp,
        parse_mode=ParseMode.HTML,
        caption=caption,
    )
    tmp.close()

    return result_media

def form_rich_html_from_post(post: PostData, caption: str) -> str:
    media_html = "".join([f'<img src="{media.url}"/>' for media in post.attached_media])
    if len(post.attached_media) > 1:
        # tg-collage with a single item breaks on iphones
        media_html = f"<tg-collage>{media_html}</tg-collage>"
    caption = caption.replace('\n', '<br>')
    return f"{media_html}{caption}"


class TwitterExtractor(Handler):
    hosts = {
        "twitter.com": "twitter.com",
        "fxtwitter.com": "twitter.com",
        "vxtwitter.com": "twitter.com",
        "x.com": "twitter.com",
        "fixupx.com": "twitter.com",
        "vk.com": "vk.com",
        "vk.ru": "vk.com",
        "m.vk.com": "vk.com",
        "vkvideo.ru": "vk.com",
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
            if host in self.hosts and _check_is_post_link(self.hosts[host], url):
                self.hidden.append(self._check_to_hide(url))
                host = self.hosts[host]
                self.normalized_urls.append(
                    urlunsplit((scheme, host, path, query, None))
                )
        logger.info(self.normalized_urls)
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

    def process(self, params: list):
        posts_with_media = []
        for num, url in enumerate(params):
            scraper = select_scraper(url)
            post_data = scraper.scrape(url)
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
        has_video = False
        for i, media in enumerate(item.attached_media):
            wrapper = (
                InputMediaPhoto if media.type == MediaType.IMAGE else InputMediaVideo
            )
            
            if media.type != MediaType.IMAGE:
                has_video = True
            
            media_group.append(
                wrapper(
                    media.url if not media.downloaded else get_bytes(media.downloaded),
                    parse_mode=ParseMode.HTML,
                    # only add the caption to image #0
                    caption=caption if i == 0 else None,
                )
            )

        return media_group, has_video

    def answer(self, result: list[PostData]):
        for num, item in enumerate(result):
            if not item.attached_media:
                continue

            caption = item.get_caption(
                original=self.message.link,
                author=self.user.full_name,
            )

            logger.debug(f"Caption length: {len(caption)}")

            media_group, group_has_video = self._form_media_group(item, caption)
            complete = False
            tries = 0
            while not complete and tries < 10:
                logger.info(
                    f"Sending media group... {media_group}, {[(media.caption if hasattr(media, 'caption') else '---', media.media, media.parse_mode) for media in media_group]}"
                )
                try:
                    # if group_has_video:
                    self.chat.send_media_group(
                        media=media_group,
                        disable_notification=True,
                        api_kwargs={"has_spoiler": True} if self.hidden[num] else None,
                    )

                    # else:
                        # caption_long = item.get_caption(
                            # original=self.message.link,
                            # author=self.user.full_name,
                            # length_limit=8000,
                        # )
                        # logger.info(form_rich_html_from_post(item, caption_long))
                        # r = requests.post(
                            # f"https://api.telegram.org/bot{config.token}/sendRichMessage",
                            # json={
                                # "chat_id": self.chat.id,
                                # "rich_message": {
                                    # "html": form_rich_html_from_post(item, caption_long),
                                # }
                            # },
                            # timeout=60,
                        # )
                        # r.raise_for_status()
                    
                    complete = True
                except (BadRequest, NetworkError) as exc:
                    logger.warning(exc.message)
                    tries += 1
                    logger.debug(f"Failed... try #{tries}")

                    if exc.message.startswith(
                        "urllib3 HTTPError The operation did not complete (write)"
                    ):
                        continue
                    elif (
                        exc.message in (
                            'Failed to send message #1 with the error message "wrong file identifier/http url specified"',
                            'Failed to send message #1 with the error message "webpage_media_empty"',
                            'Failed to send message #1 with the error message "webpage_curl_failed"',
                            'Timed out',
                        ) or exc.message.startswith("Can't parse inputmedia: can't parse entities")
                    ):
                        complete = True
                        for i, media_item in enumerate(media_group):
                            if isinstance(media_item.media, str) and isinstance(media_item, InputMediaVideo):
                                media_group[i] = load_media_video_from_url(
                                    media_item.media,
                                    (
                                        media_item.caption
                                        if hasattr(media_item, "caption")
                                        else None
                                    ),
                                )
                                complete = False
                    else:
                        logger.error(f"Failed to send media group: {exc.message}")
                        complete = True
                        self.chat.send_message(
                            f"<code>Не удалось загрузить медиа...</code>\n\n{caption}",
                            parse_mode=ParseMode.HTML,
                            disable_notification=True,
                        )
