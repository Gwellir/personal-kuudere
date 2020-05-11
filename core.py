from jikanpy import Jikan

from db_wrapper2 import DataInterface
from handlers import HandlersStructure
from jobs import BotJobs
from feed_parser import TorrentFeedParser
from list_parser import ListImporter


class BotCore:
    def __init__(self, updater):
        self.di = DataInterface()
        self.jikan = Jikan()
        self.feed_parser = TorrentFeedParser(self.jikan, self.di)
        self.list_importer = ListImporter(self.jikan, self.di)
        self.handlers = HandlersStructure(updater, self.jikan, self.di)
        self.jobs = BotJobs(updater, self.feed_parser, self.list_importer, self.di)
