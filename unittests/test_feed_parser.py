from datetime import datetime
from unittest import TestCase

from jikanpy import Jikan

import config
from parsers.feed_parser import TorrentFeedParser, parse_feed_title, title_compare
from utils.db_wrapper2 import BaseRelations, DataInterface

ji = Jikan(**config.jikan_params)
di = DataInterface(BaseRelations())
tfp = TorrentFeedParser(ji, di)


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

        self.assertIsNotNone(title_compare(variants, title))
