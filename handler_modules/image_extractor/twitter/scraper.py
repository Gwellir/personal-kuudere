import json 
import logging
import re
import subprocess
from functools import lru_cache
from http import HTTPStatus
from time import sleep
from typing import Optional

import jmespath
import requests
from yt_dlp import YoutubeDL

import config
from handler_modules.image_extractor.base_scraper import BaseScraper
from handler_modules.image_extractor.models import PostData

logger = logging.getLogger("handler.x_scraper")

MAX_SIZE_MB = 20
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

def get_content_length(url, timeout=10):
    logger.debug(f"Getting content length for {url}...")
    try:
        r = requests.head(
            url,
            allow_redirects=True,
            timeout=timeout,
            proxies={
                "https": config.proxy_auth_url,
                "http": config.proxy_auth_url,
            },
        )
        size = r.headers.get("Content-Length")
        return int(size) if size else None
    except Exception:
        return None

def pick_adequate_video_size(info: dict, max_bytes: int = MAX_SIZE_BYTES):
    logger.debug(f"Trying to select http- video around 720p sub {MAX_SIZE_MB}MB...")
    formats = info.get("formats", [])
    formats.sort(key=lambda x: x["tbr"], reverse=True)
    candidates = []

    for f in formats:
        if not f.get("format_id", "").startswith("http-"):
            continue

        if not f.get("url"):
            continue
        
        # if there is no video with ~720p quality or higher, we'll pick first (best) available
        if candidates and f.get("height") < 700:
            continue

        candidates.append({
            "url": f["url"],
            "width": f.get("width"),
            "height": f.get("height"),
            "bitrate": f.get("tbr", 0),
        })

    if not candidates:
        return None

    # Find best actual file under limit
    for c in candidates:
        size = get_content_length(c["url"])

        logger.debug(f"size for {c['url']}: {size}")
        if size is None:
            continue

        if size <= max_bytes:
            c["size_bytes"] = size
            c["size_mb"] = round(size / 1024 / 1024, 2)
            return c

    return candidates[-1]

def pick_all_adequate_for_post(tweet_url):
    logger.debug(f"Trying to get all adequate video formats for {tweet_url}.")
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookies_from_browser": "firefox",
        "proxy": config.proxy_auth_url,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(tweet_url, download=False)

    if "entries" in info:
        videos = info["entries"]
    else:
        videos = (info,)

    return [pick_adequate_video_size(v) for v in videos]


class TwitterScraper(BaseScraper):
    @lru_cache(maxsize=30)
    def scrape(self, url: str) -> PostData | None:
        url = self._clean_url(url)
        post_data = self._vx_scrape_tweet(url)
        logger.debug(f"got data from vx api: {post_data}")
        qrt_data = None
        if post_data:
            converted_data = self._convert(post_data)
            logger.debug(f"converted to common format: {converted_data}")
            if (post_data["qrtURL"] is not None) and (post_data["qrt"] is not None):
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
        if match := re.search(r"(https://x.com/\w+/status/\d+).*", url):
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
            language: lang,
            reply_count: replies,
            retweet_count: retweets,
            text: text,
            translated: translation,
            id: conversationID,
            name: user_name,
            screen_name: user_screen_name,
            sensitive: possibly_sensitive
        }""",
            post_data,
        )
        
        if result["url"].find("https://twitter.com/") >= 0:
            result["url"] = result["url"].replace("https://twitter.com/", "https://x.com/")

        result["name"] = (
            f'{result["screen_name"]} ({result["name"]})'
            if result["name"]
            else result["screen_name"]
        )

        return result

    @staticmethod
    def _vx_scrape_tweet(url: str) -> Optional[dict]:
        """Scrape a twitter page using vxtwitter API"""

        api_url = url.replace("https://x.com", "https://api.vxtwitter.com/en") + "/"
        retries = 0
        completed = False
        while not completed and retries < 5:
            res = requests.get(
                api_url,
                timeout=20,
                proxies={
                    "https": config.proxy_auth_url,
                    "http": config.proxy_auth_url,
                },
                headers={
                    "user-agent": config.vxtwitter_user_agent,
                },
            )
            if res.status_code == HTTPStatus.OK:
                result_data = res.json()
                video_media_list = [media for media in result_data["media_extended"] if media["type"] == "video"]
                if video_media_list:
                    adequate_video = pick_all_adequate_for_post(url)
                for i, v_m in enumerate(video_media_list):
                    v_m["url"] = adequate_video[i]["url"]
                completed = True
                return result_data
            elif res.status_code in (HTTPStatus.INTERNAL_SERVER_ERROR,):
                sleep(1)
                retries += 1
            else:
                return

