from jikanpy import Jikan
from AnimeBotHandlers import HandlersStructure
from AnimeBotJobs import BotJobs
from AnimeBotDBWrapper import DBInterface
from AnimeBotFeedParser import TorrentFeedParser
from AnimeBotListParser import ListImporter


class BotCore:
    def __init__(self, updater):
        self.ani_db = DBInterface()
        self.jikan = Jikan()
        self.feed_parser = TorrentFeedParser(self.ani_db, self.jikan)
        self.list_importer = ListImporter(self.ani_db, self.jikan)
        self.handlers = HandlersStructure(updater, self.ani_db, self.jikan)
        self.jobs = BotJobs(updater, self.ani_db, self.feed_parser, self.list_importer)
