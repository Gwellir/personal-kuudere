import logging
import re
from functools import lru_cache
from http import HTTPStatus
from time import sleep
from typing import Optional

import jmespath
import requests

import config
from handler_modules.image_extractor.base_scraper import BaseScraper
from handler_modules.image_extractor.models import PostData

logger = logging.getLogger("handler.x_scraper")


class TwitterScraper(BaseScraper):
    def scrape(self, url: str) -> PostData | None:
        url = self._clean_url(url)
        post_data = self._vx_scrape_tweet(url)
        logger.debug(f"got data from vx api: {post_data}")
        qrt_data = None
        if post_data:
            converted_data = self._convert(post_data)
            logger.debug(f"converted to common format: {converted_data}")
            if post_data["qrtURL"] is not None:
                qrt_data = self._convert(post_data["qrt"])
                logger.debug(f"got QRT data: {qrt_data}")
                converted_data["qrt"] = qrt_data
            if converted_data["attached_media"]:
                if converted_data["attached_media"][0]["type"] == "gif":
                    converted_data["attached_media"][0]["type"] = "video"
            elif qrt_data and qrt_data["attached_media"]:
                converted_data["attached_media"] = qrt_data["attached_media"]

            return PostData.model_validate(converted_data)

    def _clean_url(self, url: str) -> str:
        if match := re.search(r"(https://twitter.com/\w+/status/\d+).*", url):
            url = match.group(1)
        return url

    @staticmethod
    def _convert(post_data):
        result = jmespath.search(
            """{
            url: tweetURL,
            created_at: date,
            attached_media: media_extended[],
            favorite_count: likes,
            reply_count: replies,
            retweet_count: retweets,
            text: text,
            id: conversationID,
            name: user_name,
            screen_name: user_screen_name,
            sensitive: possibly_sensitive
        }""",
            post_data,
        )

        result["name"] = (
            f'{result["screen_name"]} ({result["name"]})'
            if result["name"]
            else result["screen_name"]
        )

        return result

    @staticmethod
    @lru_cache()
    def _vx_scrape_tweet(url: str) -> Optional[dict]:
        """Scrape a twitter page using vxtwitter API"""

        api_url = url.replace("twitter.com", "api.vxtwitter.com") + "/"
        retries = 0
        completed = False
        while not completed and retries < 5:
            res = requests.get(
                api_url,
                proxies={
                    "https": config.proxy_auth_url,
                    "http": config.proxy_auth_url,
                },
            )
            if res.status_code == HTTPStatus.OK:
                completed = True
                return res.json()
            elif res.status_code in (HTTPStatus.INTERNAL_SERVER_ERROR,):
                sleep(1)
                retries += 1
            else:
                return

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