# get anime info, including by shortname
# get user lists
# get season lists

from datetime import datetime
from pprint import pprint
from time import sleep

import requests
import simplejson
from jikanpy import exceptions

import config
from handlers import UtilityFunctions
from utils.anime_lookup import AnimeLookup
from utils.anime_synonyms import Synonyms
from utils.db_wrapper2 import BaseRelations, DataInterface
from utils.exporter import ListExtractor
from utils.jikan_custom import JikanCustom

PAGE_SIZE = 300
AL_URL = "https://graphql.anilist.co"
AL_USER_QUERY = """
query ($name: String) { # Define which variables will be used in the query (id)
  User (search: $name) { # Insert our variables into the query arguments (id) (type: ANIME is hard-coded in the query)
    id
    name
    about
  }
}
"""
AL_LIST_QUERY = """
query ($username: String, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            total
            currentPage
            lastPage
            hasNextPage
            perPage
        }
        mediaList (userName: $username, type: ANIME) {
            mediaId
            media {
                idMal
                title {romaji}
                format
                episodes
                status
            }
            status
            progress
            score
        }
    }
}
"""
MONTH_TO_SEASON = {
    0: "fall",
    1: "winter",
    2: "winter",
    3: "winter",
    4: "spring",
    5: "spring",
    6: "spring",
    7: "summer",
    8: "summer",
    9: "summer",
    10: "fall",
    11: "fall",
    12: "fall",
}


class ListImporter:
    def __init__(self, jikan, data_interface, anime_lookup, synonyms, autistic=False):
        """
        Initializes requirements for list parser

        :param jikan:
        :param data_interface: DataInterface DB connector instance
        :type data_interface: :class:`db_wrapper2.DataInterface`
        """
        self.jikan = jikan
        self.di = data_interface
        self.synonyms = synonyms
        self.al = anime_lookup
        if autistic:
            self.jikan = JikanCustom()
            self.br = BaseRelations()
            self.di = DataInterface(self.br)
            self.synonyms = Synonyms(self.di)
            self.al = AnimeLookup(self.jikan, self.di)
        self.uf = UtilityFunctions(self.di, self.al)

    # call this
    def update_all(self):
        self.update_ani_list_status()
        self.update_mal_list_status()
        ListExtractor(self.di.br, self.di).save_season_stats_as_json()

    def get_anime_season_mal(self, y=None, s=None, later=False, shift=0):
        if later:
            seasonal_anime_response = self.jikan.season_later()
        else:
            if shift != 0:
                shifted_month = datetime.now().month + shift * 3
                season = MONTH_TO_SEASON[(12 + shifted_month % 12) % 12]
                year = datetime.now().year + (shifted_month - 1) // 12
            elif not y and not s:
                year = datetime.now().year
                season = MONTH_TO_SEASON[datetime.now().month]
            else:
                year = y
                season = s
            seasonal_anime_response = self.jikan.season(year=year, season=season)
        seasonal_anime = seasonal_anime_response["anime"]
        print(len(seasonal_anime))
        for item in seasonal_anime:
            print(
                f"{item['mal_id']:>5}",
                item["airing_start"][:10] if item["airing_start"] else None,
                item["type"],
                item["score"],
                item["title"],
            )

        season_name = None if later else f"{season} {year}".capitalize()
        return seasonal_anime, season_name

    def format_anilist_response(self, answer):
        page_info = answer["data"]["Page"]["mediaList"]
        airing_status_dict = {
            "FINISHED": 2,
            "RELEASING": 1,
            "NOT_YET_RELEASED": 3,
        }
        user_status_dict = {
            "CURRENT": 1,
            "COMPLETED": 2,
            "PAUSED": 3,
            "DROPPED": 4,
            "PLANNING": 6,
        }
        mal_adapted = [
            {
                "mal_id": item["media"]["idMal"],
                "title": item["media"]["title"]["romaji"],
                "type": item["media"]["format"]
                if item["media"]["format"] != "TV_SHORT"
                else "TV",
                "watching_status": user_status_dict[item["status"]],
                "watched_episodes": item["progress"],
                "total_episodes": item["media"]["episodes"],
                "score": item["score"],
                "airing_status": airing_status_dict[item["media"]["status"]],
            }
            for item in page_info
            if item["media"]["idMal"]
        ]
        return mal_adapted

    def get_animelist_anilist(self, user):
        # answer = user_list_load(user)
        answer = None
        curr_page = 1
        anime_list = []
        err_count = 0
        if not answer:
            while err_count < config.API_ERROR_LIMIT:
                variables = {
                    "username": user,
                    "page": curr_page,
                    "perPage": 50,
                }
                try:
                    response = requests.post(
                        AL_URL, json={"query": AL_LIST_QUERY, "variables": variables}
                    )
                    answer = response.json()
                    sleep(1)
                    print(curr_page, err_count)
                    anime_list += self.format_anilist_response(answer)
                    has_next = answer["data"]["Page"]["pageInfo"]["hasNextPage"]
                    err_count = 0
                except simplejson.errors.JSONDecodeError:
                    answer = {}
                    anime_list = []
                    break
                except exceptions.APIException:
                    err_count += 1
                    continue
                curr_page += 1
                if not has_next:
                    break
            if err_count == config.API_ERROR_LIMIT:
                anime_list = []
        print(len(anime_list), "items received.")
        return anime_list

    def get_animelist_mal(self, user):
        length = user["anime_stats"]["total_entries"]
        print(user["username"], length)
        # answer = user_list_load(user)
        answer = None
        curr_page = 0
        anime_list = []
        if not answer:
            while curr_page < length / PAGE_SIZE:
                answer = self.jikan.user(
                    username=user["username"],
                    request="animelist",
                    argument="all",
                    page=curr_page + 1,
                    # parameters={'sort': 'descending', 'order_by': 'score'}
                )
                print(curr_page)
                anime_list += answer["anime"]
                curr_page += 1
                if not answer:
                    break
        test_set = set()
        checked_list = []
        for item in anime_list:
            if item["mal_id"] not in test_set:
                test_set.add(item["mal_id"])
                checked_list.append(item)
            else:
                print(item["title"], item["mal_id"])
        #     print(f"{item['mal_id']:<5} {item['type']:<5} {item['score']:>2} {item['title']}")
        print(len(anime_list), "items received.")
        return checked_list

    def update_mal_list_status(self, nick=None):
        if not nick:
            userlist_mal = self.di.select_service_users_ids("MAL").all()
        else:
            userlist_mal = [(nick, None)]
        for user_entry in userlist_mal:
            user = self.jikan.user(username=user_entry[0])
            print(user["username"], "-> got profile data")
            if not user_entry[1]:
                self.di.update_users_service_id_for_service_nick(
                    user["user_id"], user["username"]
                )
            alist = self.get_animelist_mal(user)
            have_user = self.di.select_user_is_in_list_status(user["user_id"]).first()
            if alist and have_user:
                self.di.delete_list_by_user_id(user["user_id"])
            elif not alist:
                return False
            self.check_anime_table_has_anime(alist)

            self.di.insert_new_animelist(user["user_id"], alist)

    def check_anime_table_has_anime(self, alist):
        anime_ids = set([anime["mal_id"] for anime in alist])
        all_ids = set([e[0] for e in self.di.select_all_anime_ids().all()])
        missing = anime_ids - all_ids
        pprint(missing)
        lost = set()
        for anime_id in missing:
            anime = self.al.get_anime_by_aid(anime_id)
            if not anime:
                lost.add(anime_id)
        return lost

    def update_ani_list_status(self, nick=None):
        if not nick:
            userlist_ani = self.di.select_service_users_ids("Anilist").all()
        else:
            userlist_ani = [(nick, None)]
        for user_entry in userlist_ani:
            print(user_entry[0], "-> got profile data")
            if not user_entry[1]:
                variables = {
                    "name": user_entry[0],
                }
                response = requests.post(
                    AL_URL, json={"query": AL_USER_QUERY, "variables": variables}
                )
                answer = response.json()
                user_id = answer["data"]["User"]["id"]
                print(user_id)
                sleep(config.JIKAN_DELAY)
                self.di.update_users_service_id_for_service_nick(user_id, user_entry[0])
            else:
                user_id = user_entry[1]
            alist = self.get_animelist_anilist(user_entry[0])
            # todo prevent service id collisions here
            have_user = self.di.select_user_is_in_list_status(user_id)
            if alist and have_user:
                self.di.delete_list_by_user_id(user_id)
            elif not alist:
                return False
            lost = self.check_anime_table_has_anime(alist)

            self.di.insert_new_animelist(
                user_id, [a for a in alist if not a["mal_id"] in lost]
            )

    def update_seasonal(self):
        curr_season, season_name = self.get_anime_season_mal()
        self.base_update(curr_season, season_name)

        prev_season, season_name = self.get_anime_season_mal(shift=-1)
        self.base_update(prev_season, season_name)

        next_season, season_name = self.get_anime_season_mal(shift=1)
        self.base_update(next_season, season_name)
        # next_2_season = self.get_anime_season_mal(shift=2)
        # self.base_update(next_2_season)

        later_season, season_name = self.get_anime_season_mal(later=True)
        self.base_update(later_season, None)
        self.synonyms.extract_synonyms()

    def has_changed(self, anime, session):
        stored_entry = self.di.select_anime_by_id(anime["mal_id"], sess=session).first()
        if not stored_entry:
            return True
        elif (
            anime["title"] != stored_entry.title
            or anime["synopsis"] != stored_entry.synopsis
            or anime["type"] != stored_entry.show_type
            or (
                anime["airing_start"]
                and (
                    not stored_entry.started_at
                    or anime["airing_start"][:10] != str(stored_entry.started_at)[:10]
                )
            )
            or anime["episodes"] != stored_entry.episodes
            or anime["score"] != stored_entry.score
            or stored_entry.status == "Currently Airing"
            or stored_entry.status == "Not yet aired"
        ):
            return True
        else:
            return False

    def base_update(self, anime_list, season_name):
        genre_list = [g[0] for g in self.di.select_genres().all()]
        licensor_list = [lic[0].lower() for lic in self.di.select_licensors().all()]
        producer_list = [p[0] for p in self.di.select_producers().all()]
        print(producer_list)
        session = self.di.br.get_session()
        for anime in anime_list:
            print(f'> {anime["title"]}')
            if anime["genres"]:
                new_genres = [
                    genre
                    for genre in anime["genres"]
                    if genre["mal_id"] not in genre_list
                ]
                self.di.insert_new_genres(new_genres, session)
                genre_list.extend([genre["mal_id"] for genre in new_genres])
            if anime["licensors"]:
                new_licensors = [
                    licensor
                    for licensor in anime["licensors"]
                    if licensor.lower() not in licensor_list
                ]
                print(new_licensors)
                self.di.insert_new_licensors(new_licensors, session)
                licensor_list.extend([licensor["name"] for licensor in new_licensors])
            if anime["producers"]:
                new_producers = [
                    producer
                    for producer in anime["producers"]
                    if producer["mal_id"] not in producer_list
                ]
                print(new_producers)
                self.di.insert_new_producers(new_producers, session)
                producer_list.extend([producer["mal_id"] for producer in new_producers])
            # if not ani_db.select('mal_aid', 'anime', f"mal_aid = %s", [anime['mal_id']]):
            if self.has_changed(anime, session):
                remote_entry = self.jikan.anime(anime["mal_id"])
                pprint(remote_entry)
                self.di.upsert_anime_entry(remote_entry, session)
                # new_list.append(anime)
                self.di.insert_new_axg(anime, session)
                self.di.insert_new_axp(anime, session)
                self.di.insert_new_axl(anime, session)
            # sleep(2)
        if season_name:
            cross_data = [
                {
                    "mal_aid": anime["mal_id"],
                    "season": season_name,
                }
                for anime in anime_list
            ]
            self.di.update_seasonal_data(cross_data, season_name, session)
        session.commit()
        session.close()


if __name__ == "__main__":
    li = ListImporter(None, None, None, None, autistic=True)
    # li.update_mal_list_status("DrumBox")
    # li.update_all()
    # li.get_anime_season_mal()
    li.update_seasonal()
    # br = BaseRelations()
    # ListExtractor(br, DataInterface(br)).save_season_stats_as_json()
