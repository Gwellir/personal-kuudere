import datetime
import http.client
from time import sleep
from typing import Any, Dict, Optional

import jikanpy
import requests
import simplejson

import config
from utils.seasons import get_season_from_date

LAST_HIT = datetime.datetime(1970, 1, 1)


def retried(func):
    def wrapped(*args, **kwargs):
        global LAST_HIT
        result = done = None
        err_count = 0
        while not done and err_count <= config.API_ERROR_LIMIT:
            try:
                result = func(*args, **kwargs)
                done = True
                if (
                    interval := datetime.datetime.now() - LAST_HIT
                ) < datetime.timedelta(seconds=config.JIKAN_DELAY):
                    print(
                        f"Waiting out a delay: {config.JIKAN_DELAY - interval.seconds} seconds..."
                    )
                    sleep(config.JIKAN_DELAY - interval.seconds)
                LAST_HIT = datetime.datetime.now()
            except simplejson.errors.JSONDecodeError:
                break
            except (
                jikanpy.exceptions.APIException,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
                ConnectionResetError,
                http.client.RemoteDisconnected,
            ) as e:
                if e.args[0] in (
                    404,
                    504,
                ):
                    raise e
                err_count += 1
                wait_s = config.JIKAN_DELAY * err_count
                print(
                    f"API {e} inaccessible x{err_count}: waiting for {wait_s} seconds..."
                )
                sleep(wait_s)
                continue

        return result

    return wrapped


class JikanCustom:
    """
    Custom adapter for Jikan implementing custom timeout Session
    as well as processing of connection errors
    """

    allowed_anime_cols = []

    def __init__(self, *args, **kwargs):
        from orm.ORMWrapper import Anime

        self._jikan = jikanpy.Jikan(*args, **kwargs, **config.jikan_params)
        self.allowed_anime_cols = set(Anime.__table__._columns.keys()) | {"__len__"}
        self._anime = None
        self._character = None
        self._user = None
        self._season = None
        self._search_results = None
        self._relations = None

    @staticmethod
    def _get_formatted_relations(data):
        relations: Dict[str, Any] = dict()
        if data:
            for entry in data:
                relations[entry.get("relation")] = entry.get("entry")

        return relations

    def _rename_anime_fields(self):
        diffs = {
            "mal_id": "mal_aid",
            "type": "show_type",
        }
        for key, value in diffs.items():
            self._anime[value] = self._anime.pop(key)

        return self

    def _convert_anime_aired(self):
        self._anime["started_at"] = self._anime["ended_at"] = None
        aired = self._anime.pop("aired")
        if _from := aired.get("from"):
            self._anime["started_at"] = _from[:10]
        if to := aired.get("to"):
            self._anime["ended_at"] = to[:10]

        return self

    def _convert_anime_broadcast(self):
        if broadcast_data := self._anime.get("broadcast"):
            self._anime["broadcast"] = broadcast_data.get("string")

        return self

    def _add_anime_relations(self):
        self._anime["related"] = self._relations

        return self

    def _add_anime_image_url(self):
        if images := self._anime.get("images"):
            self._anime["image_url"] = images.get("jpg").get("image_url")

        return self

    def _add_anime_trailer_url(self):
        if trailer := self._anime.get("trailer"):
            self._anime["trailer_url"] = trailer.get("url")

        return self

    def _add_anime_premiered(self):
        if started_time := self._anime.get("started_at"):
            dtime = datetime.datetime.fromisoformat(started_time)
            self._anime["premiered"] = get_season_from_date(
                dtime, for_show=True
            ).capitalize()

        return self

    def _add_anime_op_eds(self):
        if themes := self._anime.get("theme"):
            self._anime["opening_themes"] = themes.get("openings")
            self._anime["ending_themes"] = themes.get("endings")

        return self

    def _remove_anime_spare_fields(self):
        all_keys = set(self._anime.keys())
        for key in all_keys - self.allowed_anime_cols:
            self._anime.pop(key)

        return self

    def _format_anime(self):
        return (
            self._rename_anime_fields()
            ._convert_anime_aired()
            ._convert_anime_broadcast()
            ._add_anime_relations()
            ._add_anime_image_url()
            ._add_anime_trailer_url()
            ._add_anime_premiered()
            ._add_anime_op_eds()
            ._remove_anime_spare_fields()
        )

    @retried
    def relations(self, *args, **kwargs):
        self._relations = self._get_formatted_relations(
            self._jikan.anime(*args, extension="relations", **kwargs).get("data")
        )
        return self._relations

    @retried
    def anime(self, *args, **kwargs):
        self._anime = self._jikan.anime(*args, extension="full", **kwargs).get("data")
        if not self._anime:
            self._anime = self._jikan.anime(*args, **kwargs).get("data")
            self._relations = {}
        else:
            self._relations = self._get_formatted_relations(
                self._anime.get("relations")
            )
        self._format_anime()

        return self._anime

    @retried
    def character(self, *args, **kwargs):
        return self._jikan.character(*args, **kwargs).get("data")

    @retried
    def search(self, type_, query, *args, **kwargs):
        results = self._jikan.search(type_, query, *args, **kwargs).get("data")
        if type_ == "anime":
            formatted_results = []
            for res in results:
                self._anime = res
                self._relations = self._get_formatted_relations(
                    self._anime.get("relations")
                )
                self._format_anime()
                formatted_results.append(self._anime)
            results = formatted_results

        return results

    def season(self, page: Optional[int] = None, *args, **kwargs):
        @retried
        def get_season_page():
            return self._jikan.season(page=page, *args, **kwargs).get("data")

        done = False
        page = 1
        data = []
        while not done:
            results = get_season_page()
            data.extend(results)

            if results:
                page += 1
            else:
                done = True

        return data

    def season_later(self, page: Optional[int] = None, *args, **kwargs):
        return self.season(page=page, upcoming=True, *args, **kwargs)

    @retried
    def user(self, *args, **kwargs):
        return self._jikan.user(*args, **kwargs).get("data")

    def _get_normalized_animelist(self, results):
        airing_dict = {
            "finished_airing": 2,
            "currently_airing": 1,
            "not_yet_aired": 3,
        }
        status_dict = {
            "watching": 1,
            "completed": 2,
            "on_hold": 3,
            "dropped": 4,
            "plan_to_watch": 6,
        }
        normalized_results = []
        for entry in results:
            anime = entry.get("node")
            list_status = entry.get("list_status")
            normalized_results.append(
                dict(
                    mal_aid=anime.get("id"),
                    title=anime.get("title"),
                    show_type=anime.get("media_type"),
                    status=status_dict.get(list_status.get("status")),
                    watched=list_status.get("num_episodes_watched"),
                    eps=anime.get("num_episodes"),
                    score=list_status.get("score"),
                    airing=airing_dict.get(anime.get("status")),
                )
            )

        return normalized_results

    def userlist(self, username, request: str = "animelist"):
        @retried
        def get_userlist_part():
            return requests.get(
                f"{base_url}/{username}/{request}",
                headers={"X-MAL-CLIENT-ID": token},
                params=params,
                proxies={
                    "https": config.proxy_auth_url,
                    "http": config.proxy_auth_url,
                },
            ).json()

        base_url = "https://api.myanimelist.net/v2/users"
        token = config.MAL_API_TOKEN
        page_size = config.MAL_API_LIST_PAGE_SIZE
        done = False
        offset = 0
        data = []
        while not done:
            if request == "animelist":
                fields = ["media_type", "status", "list_status", "num_episodes"]
                params = dict(
                    limit=page_size,
                    offset=offset,
                    fields=",".join(fields),
                    nsfw=1,
                )
                results = get_userlist_part()
                data.extend(self._get_normalized_animelist(results.get("data")))
            else:
                raise NotImplementedError(
                    f"Userlist processing for request '{request}' is not implemented!"
                )

            if results.get("paging").get("next"):
                offset += page_size
                params["offset"] = offset
            else:
                done = True

        return data
