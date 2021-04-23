from jikanpy import Jikan

from handlers import HandlersStructure
from jobs import BotJobs
from parsers.feed_parser import TorrentFeedParser
from parsers.list_parser import ListImporter
from utils.anime_synonyms import Synonyms
from utils.db_wrapper2 import BaseRelations, DataInterface


class BotCore:
    def __init__(self, updater):
        self.br = BaseRelations()
        self.di = DataInterface(self.br)
        self.jikan = Jikan()
        self.feed_parser = TorrentFeedParser(self.jikan, self.di)
        self.synonyms = Synonyms(self.di)
        self.list_importer = ListImporter(self.jikan, self.di, self.synonyms)
        self.handlers = HandlersStructure(
            updater, self.jikan, self.di, self.list_importer
        )
        self.jobs = BotJobs(updater, self.feed_parser, self.list_importer, self.di)
