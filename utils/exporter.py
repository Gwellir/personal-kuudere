from datetime import datetime
from pprint import pprint

import simplejson

import config
from orm.ORMWrapper import ListStatus, Users, Anime, UsersXTracked, AnimeXSeasons
from utils.seasons import get_season_from_date


class ListExtractor:
    def __init__(self, base_relations, data_interface):
        self.di = data_interface
        self.br = base_relations

    def _select_full_tracking_for_imports(self):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, Users.mal_uid == ListStatus.user_id)
            .join(Anime, Anime.mal_aid == ListStatus.mal_aid)
            .join(AnimeXSeasons, AnimeXSeasons.mal_aid == Anime.mal_aid)
            .with_entities(
                Anime.mal_aid,
                AnimeXSeasons.season,
                Anime.title,
                Anime.score,
                Anime.image_url,
                Anime.trailer_url,
                Anime.show_type,
                Users.tg_nick,
                ListStatus.watched,
                ListStatus.status,
            )
        )
        session.close()

        return result

    def _select_full_tracking_for_bot(self):
        session = self.br.get_session()
        result = (
            session.query(UsersXTracked)
            .join(Users, Users.id == UsersXTracked.user_id)
            .join(Anime, Anime.mal_aid == UsersXTracked.mal_aid)
            .join(AnimeXSeasons, AnimeXSeasons.mal_aid == Anime.mal_aid)
            .with_entities(
                Anime.mal_aid,
                AnimeXSeasons.season,
                Anime.title,
                Anime.score,
                Anime.image_url,
                Anime.trailer_url,
                Anime.show_type,
                Users.tg_nick,
                UsersXTracked.last_ep,
            )
        )
        session.close()

        return result

    def get_merged_season_tracking(self, season_name):
        import_tracking = self._select_full_tracking_for_imports().filter_by(season=season_name).all()
        bot_tracking = self._select_full_tracking_for_bot().filter_by(season=season_name).all()
        pprint(import_tracking)
        pprint(bot_tracking)
        tracking_data = {}
        title_data = {}
        for entry in bot_tracking:
            tracking_data[entry[0], entry[7]] = {
                "status": 1,
                "watched": entry[8],
            }
            title_data[entry[0]] = {
                "title": entry[2],
                "image_url": entry[4],
                "score": entry[3],
                "trailer_url": entry[5],
                "type": entry[6],
            }
        for entry in import_tracking:
            tracking_data[entry[0], entry[7]] = {
                "status": entry[9],
                "watched": entry[8],
            }
            title_data[entry[0]] = {
                "title": entry[2],
                "image_url": entry[4],
                "score": entry[3],
                "trailer_url": entry[5],
                "type": entry[6],
            }
        pprint(tracking_data)
        pprint(title_data)
        tracking_list = [
            {
                "anime_id": key[0],
                "tg_nick": key[1],
                "status": entry["status"],
                "watched": entry["watched"],
            }
            for key, entry in tracking_data.items()
        ]
        title_list = [
            {
                "anime_id": key,
                "title": entry["title"],
                "image_url": entry["image_url"],
                "score": entry["score"],
                "trailer_url": entry["trailer_url"],
                "type": entry["type"],
            }
            for key, entry in title_data.items()
        ]

        return tracking_list, title_list

    def save_season_stats_as_json(self):
        season_name = get_season_from_date(datetime.now())
        # user_stats = self.di.select_extended_user_stats(season_name).all()
        tracking, titles = self.get_merged_season_tracking(season_name)
        stats_dict = {
            "updated": str(datetime.now().timestamp()),
            "season": season_name,
            "tracking": [
                {
                    "anime_id": entry["anime_id"],
                    "tg_nick": entry["tg_nick"],
                    "status": entry["status"],
                    "watched": entry["watched"],
                }
                for entry in tracking
            ],
            "anime": [
                {
                    "anime_id": anime["anime_id"],
                    "title": anime["title"],
                    "image_url": anime["image_url"],
                    "score": anime["score"],
                    "trailer_url": anime["trailer_url"],
                    "type": anime["type"],
                }
                for anime in titles
            ],
        }
        with open(config.season_stats_file, "w") as f:
            simplejson.dump(stats_dict, f)
