import os

from handler_modules.base import Handler, HandlerError
from handler_modules.voting_system.system import VotingSystem, DisplayableCharacter
from orm.ORMWrapper import VotedCharacters, SeasonalVotings


class ManageVoting(Handler):
    command = "manage_voting"

    def __init__(self):
        super().__init__()

    def parse(self, args):
        return args

    def process(self, params: list):
        if params[0] == "start":
            session = self.br.get_session()
            current_voting = session.query(SeasonalVotings).filter_by(is_current=True).first()
            candidates = (
                session.query(VotedCharacters)
                # .join(SeasonalVotings)
                .filter_by(voting=current_voting)
                .all()
            )
            participants = [DisplayableCharacter(character) for character in candidates]
            vs = VotingSystem(name=current_voting.season, items=participants)
            self.bot_data["current_voting"] = vs

            return f"Начато голосование '{vs.name}'"
        elif params[0] == "stop":
            vs = VotingSystem.get_voting(self.bot_data)
            VotingSystem.clear(self.bot_data)

            return f"Закончено голосование {vs.name}"
        elif params[0] == "advance":
            vs = VotingSystem.get_voting(self.bot_data)
            vs.advance_stage()
            if vs.is_finished:
                pass
            return f"Голосование {vs.name} переведено в стадию {vs.stage}"
