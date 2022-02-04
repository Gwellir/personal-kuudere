from orm.ORMWrapper import BaseRelations
from utils.db_wrapper2 import DataInterface


class Synonyms:
    pairs = set()

    def __init__(self, data_interface, autistic=False):
        """Takes data interface class or creates an instance when used as a standalone module.
        Updates synonym table from an updated anime table.

        :param data_interface: DataInterface DB connector instance
        :type data_interface: :class:`utils.db_wrapper2.DataInterface`
        """
        if autistic:
            br = BaseRelations()
            self.di = DataInterface(br)
        else:
            self.di = data_interface

    def add_to_synonyms(self, mal_aid, synonym):
        if synonym is None:
            return
        else:
            self.pairs.add((mal_aid, synonym))

    def extract_synonyms(self):
        synlist = self.di.select_all_possible_synonyms().all()
        for entry in synlist:
            for i in range(3):
                self.add_to_synonyms(entry[0], entry[i + 1])
            if entry[4]:
                for syn in entry[4]:
                    self.add_to_synonyms(entry[0], syn)
        old_synonyms = set(
            [
                (entry[0], entry[1].lower())
                for entry in self.di.select_existing_synonyms()
            ]
        )
        result = [
            entry
            for entry in self.pairs
            if (entry[0], entry[1].lower()) not in old_synonyms
        ]
        print(len(self.pairs), len(result), len(old_synonyms))

        for pair in result:
            self.di.insert_new_synonym(pair[0], pair[1])


if __name__ == "__main__":
    s = Synonyms(None, autistic=True)
    s.extract_synonyms()
