import datetime
import http.client
from time import sleep
from typing import Any, Dict

import jikanpy
import requests
import simplejson

import config
from utils.seasons import get_season_from_date

LAST_HIT = datetime.datetime(1970, 1, 1)


def retried(func):
    def wrapped(*args, **kwargs):
        global LAST_HIT
        result = None
        err_count = 0
        while not result and err_count <= config.API_ERROR_LIMIT:
            try:
                result = func(*args, **kwargs)
                if (
                    interval := datetime.datetime.now() - LAST_HIT
                ) < datetime.timedelta(seconds=config.JIKAN_DELAY):
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
                if e.args[0] == 404:
                    raise e
                err_count += 1
                wait_s = config.JIKAN_DELAY * err_count
                print(
                    f"JIKAN inaccessible x{err_count}: waiting for {wait_s} seconds..."
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
        self._relations = self._get_formatted_relations(self._anime.get("relations"))
        self._format_anime()

        return self._anime

    @retried
    def character(self, *args, **kwargs):
        return self._jikan.character(*args, **kwargs).get("data")

    @retried
    def search(self, *args, **kwargs):
        return self._jikan.search(*args, **kwargs).get("data")

    @retried
    def season(self, *args, **kwargs):
        return self._jikan.season(*args, **kwargs).get("data")

    @retried
    def season_later(self, *args, **kwargs):
        return self._jikan.season_later().get("data")

    @retried
    def user(self, *args, **kwargs):
        return self._jikan.user(*args, **kwargs).get("data")
