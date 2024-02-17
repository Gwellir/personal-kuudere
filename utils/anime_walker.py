from random import randint, shuffle
from time import sleep

from orm.ORMWrapper import BaseRelations, Anime
from utils.anime_lookup import AnimeLookup
from utils.db_wrapper2 import DataInterface
from utils.jikan_custom import JikanCustom

base = BaseRelations()
ji = JikanCustom()
di = DataInterface(base)
al = AnimeLookup(ji, di)

# ongoing_ids = [e[0] for e in di.select_ongoing_ids().all()]
# for _id in ongoing_ids:
#     print(uf.get_anime_by_aid(_id))


def get_anime_by_ids(ls_ids):
    shuffle(ls_ids)
    print(len(ls_ids))
    for i in range(len(ls_ids)):
        res = al.get_anime_by_aid(ls_ids[i])
        if not res:
            print("FAIL: ", ls_ids[i])
        sleep(randint(0, 2))
        if i % 30 == 29:
            print("got", i, "titles -", len(ls_ids) - i, "remaining")
            sleep(randint(60, 120))


anime_ids = [
    e[0]
    for e in base.get_session()
    .query(Anime.mal_aid)
    .filter(Anime.popularity == None)
    .all()
]

get_anime_by_ids(anime_ids)
