from datetime import datetime
from unittest import TestCase

from parsers.feed_parser import (
    TorrentFeedParser,
    get_closest_match_aid,
    parse_feed_title,
)
from utils.anime_lookup import AnimeLookup
from utils.db_wrapper2 import BaseRelations, DataInterface
from utils.jikan_custom import JikanCustom

ji = JikanCustom()
di = DataInterface(BaseRelations())
al = AnimeLookup(ji, di)
tfp = TorrentFeedParser(di, al)


class TestFeedParser(TestCase):
    #
    # def __init__(self):
    #     super().__init__()
    #     self.di = DataInterface(BaseRelations())
    #     self.jikan = Jikan()

    def test_name_parsing(self):
        title1 = "[SubsPlease] 86 - Eighty Six - 13 (1080p) [87C492A3].mkv"
        self.assertEqual(
            (
                13,
                "SubsPlease",
                "86 - Eighty Six",
                1080,
                "mkv",
            ),
            parse_feed_title(title1),
        )

        title2 = "[SubsPlease] 86 - Eighty Six - 13 (1080p) [87C492A3].mkv"
        session = di.br.get_session()
        self.assertEqual(
            (13, "SubsPlease", "86 - Eighty Six", 1080, "mkv"),
            tfp.do_recognize(
                title2,
                datetime.now(),
                "",
                0,
                session,
            ),
        )

    # def test_title_recognition(self):
    #     params1 = ("[Judas] Re:Zero kara Hajimeru Isekai Seikatsu - S02E11 [1080p][HEVC x265 10bit][Multi-Subs] (Weekly)",
    #                 "2020-09-16 20:16:55",

    def test_title_compare(self):
        title = "Tonikaku Kawaii"
        variants = [{"title": "Haikyuu!! To the Top"}]

        self.assertIsNotNone(get_closest_match_aid(variants, title))

    def test_mal_recognition(self):
        title = "Sono Bisque Doll wa Koi o Suru"

        mal_aid = tfp.get_mal_ongoing_by_title(title, 1)
        al.get_anime_by_aid(mal_aid)

    def test_check_feeds(self):
        tfp.check_feeds()
