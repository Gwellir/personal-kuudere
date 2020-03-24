from jikanpy import Jikan
from handlers import HandlersStructure
from jobs import BotJobs
from db_wrapper import DBInterface
from feed_parser import TorrentFeedParser
from list_parser import ListImporter


class BotCore:
    def __init__(self, updater):
        self.ani_db = DBInterface()
        self.jikan = Jikan()
        self.feed_parser = TorrentFeedParser(self.ani_db, self.jikan)
        self.list_importer = ListImporter(self.ani_db, self.jikan)
        self.handlers = HandlersStructure(updater, self.ani_db, self.jikan)
        self.jobs = BotJobs(updater, self.ani_db, self.feed_parser, self.list_importer)
