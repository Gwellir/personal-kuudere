from datetime import datetime, timedelta
from random import randint, shuffle
from time import sleep

from logger.logger import ANIMEBASE_LOG
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
        ANIMEBASE_LOG.info(f"{ls_ids[i]}:")
        res = al.get_anime_by_aid(ls_ids[i])
        if not res:
            print("FAIL: ", ls_ids[i])
        sleep(randint(0, 2))
        if i % 30 == 29:
            print("got", i, "titles -", len(ls_ids) - i, "remaining")
            sleep(randint(60, 120))


anime_ids = [
    e[0]
    for e in base.get_session().query(Anime.mal_aid)
    # .filter(Anime.status == "Not Yet Aired")
    .filter(Anime.synced < datetime.now() - timedelta(days=14)).all()
]

range_60000 = [i for i in range(1, 60000)]

# get_anime_by_ids(range_60000)
get_anime_by_ids(anime_ids)
# get_anime_by_ids(ongoing_ids)
