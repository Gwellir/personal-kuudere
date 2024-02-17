from functools import lru_cache
from http import HTTPStatus

import jmespath
import requests

import config
from handler_modules.image_extractor.base_scraper import BaseScraper
from handler_modules.image_extractor.models import PostData, MediaType, PostMedia


class VkScraper(BaseScraper):
    def scrape(self, url: str) -> PostData | None:
        post_data = self._vk_scrape(url)
        if post_data:
            converted_data = self._convert(post_data)
            if media_data := converted_data["attached_media"]:
                # the only video in a vk post works fine on mobile
                if (
                    converted_data["attached_media"][0]["type"] == "video"
                    and len(converted_data) == 1
                ):
                    return None

                media = []
                for item in media_data:
                    if item["type"] == "photo":
                        url = sorted(item["photo"]["sizes"], key=lambda x: x["width"])[
                            -1
                        ]["url"]
                        media.append(
                            PostMedia.model_validate(
                                dict(
                                    url=url,
                                    type=MediaType.IMAGE,
                                )
                            )
                        )
                    elif item["type"] == "video":
                        pass
                converted_data["attached_media"] = media

            converted_data["url"] = url
            converted_data["id"] = str(converted_data["id"])

            return PostData.model_validate(converted_data)

    @staticmethod
    def _convert(post_data) -> dict:
        result = jmespath.search(
            """{
            name: name,
            attached_media: attachments[],
            text: text,
            id: id,
            user_id: from_id
        }""",
            post_data,
        )

        return result

    @lru_cache()
    def _vk_scrape(self, url):
        request_url = "https://api.vk.com/method/"
        posts = url.replace("https://vk.com/wall", "")
        wall_res = requests.get(
            f"{request_url}wall.getById",
            params={
                "posts": posts,
                "extended": 0,
                "v": "5.199",
                "access_token": config.vk_token,
            },
            proxies={
                "https": config.proxy_auth_url,
                "http": config.proxy_auth_url,
            },
        )
        if wall_res.status_code == HTTPStatus.OK:
            wall_post = wall_res.json()["response"]["items"][0]
            user_name = self._get_user_name_by_id(wall_post["from_id"])
            if user_name:
                wall_post["name"] = user_name
            return wall_post
        else:
            return

    @staticmethod
    @lru_cache()
    def _get_user_name_by_id(user_id: str):
        request_url = "https://api.vk.com/method/"
        user_id = int(user_id)
        params = {
            "extended": 0,
            "v": "5.199",
            "access_token": config.vk_token,
        }
        if user_id > 0:
            method = "users.get"
            params["user_ids"] = user_id
        else:
            method = "groups.getById"
            params["group_id"] = -user_id

        user_res = requests.get(f"{request_url}{method}", params=params)
        if user_res.status_code == HTTPStatus.OK:
            if user_id > 0:
                user_data = user_res.json()["response"][0]
                return f'{user_data["first_name"]} {user_data["last_name"]}'
            else:
                user_data = user_res.json()["response"]["groups"][0]
                return user_data["name"]
