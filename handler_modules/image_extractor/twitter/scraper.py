import re
from functools import lru_cache
from http import HTTPStatus
from typing import Optional

import jmespath
import requests

import config
from handler_modules.image_extractor.base_scraper import BaseScraper
from handler_modules.image_extractor.models import PostData


class TwitterScraper(BaseScraper):
    def scrape(self, url: str) -> PostData | None:
        url = self._clean_url(url)
        post_data = self._vx_scrape_tweet(url)
        if post_data:
            converted_data = self._convert(post_data)
            if converted_data["attached_media"]:
                # the only video in a tweet works fine on mobile
                # if (
                #    converted_data["attached_media"][0]["type"] == "video"
                #    and len(converted_data) == 1
                #):
                #    return None
                if converted_data["attached_media"][0]["type"] == "gif":
                    converted_data["attached_media"][0]["type"] = "video"

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

        api_url = url.replace("twitter.com", "api.vxtwitter.com")
        res = requests.get(
            api_url,
            proxies={
                "https": config.proxy_auth_url,
                "http": config.proxy_auth_url,
            },
        )
        if res.status_code == HTTPStatus.OK:
            return res.json()
        else:
            return
