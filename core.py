from handlers import HandlersStructure
from jobs import BotJobs
from parsers.feed_parser import TorrentFeedParser
from parsers.list_parser import ListImporter
from utils.anime_lookup import AnimeLookup
from utils.anime_synonyms import Synonyms
from utils.db_wrapper2 import BaseRelations, DataInterface
from utils.jikan_custom import JikanCustom


class BotCore:
    def __init__(self, updater):
        self.base_relations = BaseRelations()
        self.data_interface = DataInterface(self.base_relations)
        self.jikan = JikanCustom()
        self.anime_lookup = AnimeLookup(self.jikan, self.data_interface)
        self.feed_parser = TorrentFeedParser(self.data_interface, self.anime_lookup)
        self.synonyms = Synonyms(self.data_interface)
        self.list_importer = ListImporter(
            self.jikan, self.data_interface, self.anime_lookup, self.synonyms
        )
        self.handlers = HandlersStructure(
            updater,
            self.jikan,
            self.data_interface,
            self.list_importer,
            self.anime_lookup,
        )
        self.jobs = BotJobs(
            updater,
            self.feed_parser,
            self.list_importer,
            self.data_interface,
            self.anime_lookup,
        )
