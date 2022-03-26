import datetime
import http.client
from time import sleep

import jikanpy
import requests
import simplejson

import config

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
        self.allowed_anime_cols = set(Anime.__table__._columns.keys())

    @retried
    def anime(self, *args, **kwargs):
        anime = self._jikan.anime(*args, **kwargs)

        diffs = {
            "mal_id": "mal_aid",
            "type": "show_type",
        }
        for key, value in diffs.items():
            anime[value] = anime.pop(key)
        anime["started_at"] = anime["ended_at"] = None
        aired = anime.pop("aired")
        if _from := aired.get("from"):
            anime["started_at"] = _from[:10]
        if to := aired.get("to"):
            anime["ended_at"] = to[:10]
        all_keys = set(anime.keys())
        for key in all_keys - self.allowed_anime_cols:
            anime.pop(key)
        return anime

    @retried
    def character(self, *args, **kwargs):
        return self._jikan.character(*args, **kwargs)

    @retried
    def search(self, *args, **kwargs):
        return self._jikan.search(*args, **kwargs)

    @retried
    def season(self, *args, **kwargs):
        return self._jikan.season(*args, **kwargs)

    @retried
    def season_later(self, *args, **kwargs):
        return self._jikan.season_later()

    @retried
    def user(self, *args, **kwargs):
        return self._jikan.user(*args, **kwargs)
