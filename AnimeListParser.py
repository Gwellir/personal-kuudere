# get anime info, including by shortname
# get user lists
# get season lists

from jikanpy import Jikan, exceptions
from pprint import pprint
from time import sleep
import simplejson
from AnimeBotDBWrapper import DBInterface
import requests

PAGE_SIZE = 300
API_ERROR_LIMIT = 4
AL_URL = 'https://graphql.anilist.co'
AL_USER_QUERY = '''
query ($name: String) { # Define which variables will be used in the query (id)
  User (search: $name) { # Insert our variables into the query arguments (id) (type: ANIME is hard-coded in the query)
    id
    name
    about
  }
}
'''
AL_LIST_QUERY = '''
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
'''


class ListImporter:
    def __init__(self):
        self.jikan = Jikan()
        self.ani_db = DBInterface()

    # call this
    def update_all(self):
        self.update_ani_list_status()
        self.update_mal_list_status()
        self.ani_db.close()

    def get_anime_season_mal(self, year, season):
        sa = self.jikan.season(year=year, season=season)
        # pprint(sa['anime'][0])
        # sa_f = filter(lambda item: not item['continuing'] and item['score'] and not item['kids'],
        #                sa['anime'])
        sa_f = filter(lambda item: item['score'] and item['kids'], sa['anime'])
        sa_fs = sorted(sa_f, key=lambda item: item['mal_id'], reverse=False)
        print(len(sa_fs))
        for item in sa_fs:
            print(f"{item['mal_id']:>5}", item['airing_start'][:10] if item['airing_start'] else None, item['type'],
                  item['score'], item['title'], )
        return sa_fs

    def get_animelist_anilist(self, user):
        # answer = user_list_load(user)
        answer = None
        curr_page = 1
        anime_list = []
        err_count = 0
        if not answer:
            while err_count < API_ERROR_LIMIT:
                variables = {
                    'username': user,
                    'page': curr_page,
                    'perPage': 50
                }
                try:
                    response = requests.post(AL_URL, json={'query': AL_LIST_QUERY, 'variables': variables})
                    answer = response.json()
                    sleep(1)
                    print(curr_page, err_count)
                    page_info = answer['data']['Page']['mediaList']
                    airing_status_dict = {
                        'FINISHED': 2,
                        'RELEASING': 1,
                        'NOT_YET_RELEASED': 3
                    }
                    user_status_dict = {
                        'CURRENT': 1,
                        'COMPLETED': 2,
                        'PAUSED': 3,
                        'DROPPED': 4,
                        'PLANNING': 6
                    }
                    mal_adapted = [{
                        'mal_id': item['media']['idMal'],
                        'title': item['media']['title']['romaji'],
                        'type': item['media']['format'] if item['media']['format'] != 'TV_SHORT' else 'TV',
                        'watching_status': user_status_dict[item['status']],
                        'watched_episodes': item['progress'],
                        'total_episodes': item['media']['episodes'],
                        'score': item['score'],
                        'airing_status': airing_status_dict[item['media']['status']]
                    } for item in page_info]
                    anime_list += mal_adapted
                    has_next = answer['data']['Page']['pageInfo']['hasNextPage']
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
            if err_count == API_ERROR_LIMIT:
                anime_list = []
        # for item in anime_list:
        #     print(f"{item['mal_id']:<5} {item['type']:<5} {item['score']:>2} {item['title']}")
        print(len(anime_list), 'items received.')
        return anime_list

    def get_animelist_mal(self, user):
        length = user['anime_stats']['total_entries']
        print(user['username'], length)
        # answer = user_list_load(user)
        answer = None
        curr_page = 0
        anime_list = []
        err_count = 0
        if not answer:
            while curr_page < length/PAGE_SIZE and err_count < API_ERROR_LIMIT:
                try:
                    answer = self.jikan.user(username=user['username'], request='animelist', argument='all',
                                             page=curr_page + 1, parameters={'sort': 'descending', 'order_by': 'score'})
                    sleep(2)
                    print(curr_page, err_count)
                    anime_list += answer['anime']
                    err_count = 0
                except simplejson.errors.JSONDecodeError:
                    answer = {}
                    anime_list = []
                    break
                except exceptions.APIException:
                    err_count += 1
                    continue
                curr_page += 1
            if err_count == API_ERROR_LIMIT:
                anime_list = []
        # for item in anime_list:
        #     print(f"{item['mal_id']:<5} {item['type']:<5} {item['score']:>2} {item['title']}")
        print(len(anime_list), 'items received.')
        return anime_list

    def update_mal_list_status(self):
        userlist_mal = self.ani_db.select('mal_nick, mal_uid', 'users', 'service = %s', ['MAL'])
        # userlist_mal = [('unambo', None)]
        for user_entry in userlist_mal:
            user = self.jikan.user(username=user_entry[0])
            pprint(user)
            sleep(2)
            print(user['username'], '-> got profile data')
            if not user_entry[1]:
                self.ani_db.update('users', 'mal_uid = %s', [user['user_id']], 'mal_nick = %s', [user['username']])
            alist = self.get_animelist_mal(user)
            have_user = self.ani_db.select('user_id', 'list_status', 'user_id = %s', [user['user_id']])
            if alist and have_user:
                self.ani_db.delete('list_status', 'user_id = %s', [user['user_id']])
            elif not alist:
                self.ani_db.commit()
                return False
            self.ani_db.add_animelist(user['user_id'], alist)
            self.ani_db.commit()

    def update_ani_list_status(self):
        userlist_ani = self.ani_db.select('mal_nick, mal_uid', 'users', 'service = %s', ['Anilist'])
        for user_entry in userlist_ani:
            print(user_entry[0], '-> got profile data')
            if not user_entry[1]:
                variables = {
                    'name': user_entry[0],
                }
                response = requests.post(AL_URL, json={'query': AL_USER_QUERY, 'variables': variables})
                answer = response.json()
                user_id = answer['data']['User']['id']
                print(user_id)
                sleep(2)
                self.ani_db.update('users', 'mal_uid = %s', [user_id], 'mal_nick = %s', [user_entry[1]])
            else:
                user_id = user_entry[1]
            alist = self.get_animelist_anilist(user_entry[0])
            have_user = self.ani_db.select('user_id', 'list_status', 'user_id = %s', [user_id])
            if alist and have_user:
                self.ani_db.delete('list_status', 'user_id = %s', [user_id])
            elif not alist:
                self.ani_db.commit()
                return False
            self.ani_db.add_animelist(user_id, alist)
            self.ani_db.commit()


if __name__ == '__main__':
    li = ListImporter()
    li.update_all()

# get_animelist_mal(('unambo'), None)
# season_list = get_anime_season(2020, 'winter')
# pprint(season_list)
# new_list = []
# for anime in season_list:
#     print(anime['title'])
#     if anime['genres']:
#         new_genres = []
#         for genre in anime['genres']:
#             if not ani_db.select('mal_gid', 'genres', f"mal_gid = %s", [genre['mal_id']]):
#                 new_genres.append(genre)
#         ani_db.add_genres(new_genres)
#     # if anime['licensors']:
#     #     new_licensors = []
#     #     for licensor in anime['licensors']:
#     #         if not ani_db.select('mal_lid', 'licensors', f"mal_lid = {genre['mal_id']}"):
#     #             new_licensors.append(licensor)
#     #     ani_db.add_licensors(new_licensors)
#     if anime['producers']:
#         new_producers = []
#         for producer in anime['producers']:
#             if not ani_db.select('mal_pid', 'producers', f"mal_pid = %s", [producer['mal_id']]):
#                 new_producers.append(producer)
#         ani_db.add_producers(new_producers)
#     if not ani_db.select('mal_aid', 'anime', f"mal_aid = %s", [anime['mal_id']]):
#         new_list.append(anime)
#     if not ani_db.select('mal_aid', 'anime_x_genres', f"mal_aid = %s", [anime['mal_id']]):
#         ani_db.add_axg(anime)
#     if not ani_db.select('mal_aid', 'anime_x_producers', f"mal_aid = %s", [anime['mal_id']]):
#         ani_db.add_axp(anime)
# ani_db.add_anime(new_list)
# ani_db.commit()

