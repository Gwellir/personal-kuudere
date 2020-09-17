from MySQLdb._exceptions import IntegrityError

from db_wrapper2 import DataInterface
from ORMWrapper import *
from sqlalchemy import insert


class Synonyms:
    pairs = set()

    def __init__(self, data_interface, autistic=False):
        """Takes data interface class or creates an instance when used as a standalone module.

        :param di: DataInterface DB connector instance
        :type di: :class:`db_wrapper2.DataInterface`
        """
        if autistic:
            self.di = DataInterface()
        else:
            self.di = data_interface

    def add_to_synonyms(self, mal_aid, synonym):
        if synonym is None:
            return
        if (mal_aid, synonym) not in self.pairs:
            self.pairs.add((mal_aid, synonym))
            check = self.di.select_by_synonym_id_pair(mal_aid, synonym).first()
            if not check:
                self.di.insert_new_synonym(mal_aid, synonym)

    def extract_synonyms(self):
        synlist = self.di.select_all_possible_synonyms().all()
        for entry in synlist:
            print(f'{entry[0]}:\nmain: {entry[1]}\neng: {entry[2]}\njap: {entry[3]}')
            for i in range(3):
                self.add_to_synonyms(entry[0], entry[i+1])
            if entry[4]:
                for syn in entry[4]:
                    self.add_to_synonyms(entry[0], syn)
                    print('syn:', syn)


if __name__ == '__main__':
    s = Synonyms(None, autistic=True)
    s.extract_synonyms()
