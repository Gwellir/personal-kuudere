import logging
import re
from functools import lru_cache
from http import HTTPStatus

import jmespath
import requests

import config
from handler_modules.image_extractor.base_scraper import BaseScraper
from handler_modules.image_extractor.models import PostData, MediaType, PostMedia


logger = logging.getLogger("handler.vk.scraper")


class VkScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.request_url = "https://api.vk.com/method/"
        self.pattern = re.compile(
            r"https://vk\.com/.*(wall|photo)(-?\d+_\d+).*"
        )
        
    def scrape(self, url: str) -> PostData | None:
        post_data = self._vk_scrape(url)
        if post_data:
            # if already cached
            if "attached_media" in post_data and post_data["attached_media"]:
                return PostData.model_validate(post_data)
            if media_data := post_data["media"]:
                # the only video in a vk post works fine on mobile
                if (
                    post_data["media"][0]["type"] == "video"
                    and len(post_data) == 1
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
                post_data["attached_media"] = media

            post_data["url"] = url
            post_data["id"] = str(post_data["id"])

            return PostData.model_validate(post_data)

    @staticmethod
    def _convert_data(post_data) -> dict:
        result = jmespath.search(
            """{
            name: name,
            media: attachments[],
            text: text,
            id: id,
            user_id: from_id
        }""",
            post_data,
        )

        return result

    def _vk_scrape(self, url):
        try:
            endpoint, post_id = self.pattern.findall(url)[-1]
        except IndexError:
            return
        if endpoint == "wall":
            return self._get_wall_post(post_id)
        elif endpoint == "photo":
            return self._get_photo_post(post_id)
        else:
            return
        
    @lru_cache()
    def _get_photo_post(self, post_id):
        photo_res = requests.get(
            f"{self.request_url}photos.getById",
            params={
                "photos": post_id,
                "extended": 0,
                "v": "5.199",
                "access_token": config.vk_token,
            },
        )
        if photo_res.status_code == HTTPStatus.OK:
            photo_obj = photo_res.json()["response"][0]
            user_name = self._get_user_name_by_id(photo_obj["owner_id"])
            photo_post = dict(
                text=photo_obj["text"],
                id=photo_obj["id"],
                user_id=photo_obj["owner_id"],
                name=user_name if user_name else "",
                media=[dict(
                    photo=photo_obj,
                    type="photo",
                )],
            )

            return photo_post

    @lru_cache()
    def _get_wall_post(self, post_id):
        wall_res = requests.get(
            f"{self.request_url}wall.getById",
            params={
                "posts": post_id,
                "extended": 0,
                "v": "5.199",
                "access_token": config.vk_token,
            },
        )
        if wall_res.status_code == HTTPStatus.OK:
            wall_post = wall_res.json()["response"]["items"][0]
            user_name = self._get_user_name_by_id(wall_post["from_id"])
            if user_name:
                wall_post["name"] = user_name
            post_data = self._convert_data(wall_post)
            return post_data

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
