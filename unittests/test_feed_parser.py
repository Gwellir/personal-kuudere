from datetime import datetime
from unittest import TestCase

from jikanpy import Jikan

from parsers.feed_parser import TorrentFeedParser, parse_feed_title, title_compare
from utils.db_wrapper2 import BaseRelations, DataInterface

tfp = TorrentFeedParser(Jikan(), DataInterface(BaseRelations()))


class TestFeedParser(TestCase):
    #
    # def __init__(self):
    #     super().__init__()
    #     self.di = DataInterface()
    #     self.jikan = Jikan()

    def test_name_parsing(self):
        title1 = "[FFA] Re:Zero kara Hajimeru Isekai Seikatsu 2nd Season - 11 [1080p][HEVC][AAC].mkv"
        self.assertEqual(
            (
                "11",
                "FFA",
                "Re:Zero kara Hajimeru Isekai Seikatsu 2nd Season",
                1080,
                "mkv",
            ),
            parse_feed_title(title1),
        )

        title2 = "	[SSA] Hataraku Saibou Black - 02 [1080p].mkv"
        self.assertEqual(
            ("11", "Judas", "Re:Zero kara Hajimeru Isekai Seikatsu - S02", 1080, "mkv"),
            tfp.do_recognize(
                title2,
                datetime.now(),
                "",
                0,
            ),
        )

    # def test_title_recognition(self):
    #     params1 = ("[Judas] Re:Zero kara Hajimeru Isekai Seikatsu - S02E11 [1080p][HEVC x265 10bit][Multi-Subs] (Weekly)",
    #                 "2020-09-16 20:16:55",

    def test_title_compare(self):
        title = "Tonikaku Kawaii"
        variants = [{"title": "Haikyuu!! To the Top"}]

        self.assertIsNotNone(title_compare(variants, title))