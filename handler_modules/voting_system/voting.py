import re
from pprint import pprint

from sqlalchemy.exc import IntegrityError

from .exceptions import VotingCompletedError
from orm.ORMWrapper import Anime, SeasonalVotings

from handler_modules.base import Handler


class Voting(Handler):
    command = "voting"

    def _find_season(self, season_str):
        session = self.br.get_session()
        have_season = (
            session.query(Anime.premiered).filter_by(premiered=season_str).first()
        )
        session.close()
        if have_season:
            return True
        return False

    def _is_season(self, season_str):
        if not re.findall(r"(winter|spring|summer|fall) (20\d{2})", season_str):
            return False
        if not self._find_season(season_str):
            return False
        return True

    def _make_voting(self, season_str):
        session = self.br.get_session()
        curr_vote = session.query(SeasonalVotings).filter_by(is_current=True).first()
        if curr_vote:
            curr_vote.is_current = False

        voting = SeasonalVotings(season=season_str, is_current=True)
        session.add(voting)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            session.close()
            raise VotingCompletedError
        session.close()

        return voting

    def parse(self, args):
        pprint(args)
        if args == ["stop"]:
            pass
        elif args == ["restart"]:
            pass
        return args

    def process(self, params):
        if len(params) == 2:
            season_str = " ".join(params).strip().lower()
            if self._is_season(season_str):
                try:
                    self._make_voting(season_str)
                except VotingCompletedError:
                    return f'Голосование за сезон "{season_str}" уже существует!'
                return f'Начато голосование за сезон "{season_str}"'
