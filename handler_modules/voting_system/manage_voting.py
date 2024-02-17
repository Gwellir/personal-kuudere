import json
from time import sleep
from typing import List

from telegram import ParseMode, Bot

import config
from handler_modules.base import Handler
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
            current_voting = (
                session.query(SeasonalVotings).filter_by(is_current=True).first()
            )
            candidates = (
                session.query(VotedCharacters)
                # .join(SeasonalVotings)
                .filter_by(voting=current_voting).all()
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
            participants = list(vs.user_votes.keys())
            vs.advance_stage()
            send_results(vs, self.bot)
            generate_json(vs)
            notify_users(participants, self.bot)
            if vs.is_finished:
                pass
            return f"Голосование {vs.name} переведено в стадию {vs.stage}"


class ShowResults(Handler):
    command = "show_results"

    def __init__(self):
        super().__init__()

    def parse(self, args):
        return args

    def process(self, params: list):
        send_results(self.bot_data.get("current_voting"), self.bot)


def notify_users(userlist: List[int], bot: Bot):
    for user in userlist:
        bot.send_message(
            user,
            "Начался следующий тур голосования, чтобы принять участие, используйте команду /vote",
        )
        sleep(0.2)


def generate_json(vs):
    def data_from_position(position, current=False):
        return {
            "votes": position.current_votes if not current else None,
            "seed_number": position.seed_number,
            "item": {
                "name": position.item.get_name(),
                "title": position.item.get_category(),
                "image": f"/img/{position.item.voted_character.id}.jpg",
            },
        }

    filename = "C:\\Users\\Valion\\YandexDisk\\kuudere\\voting_stats.json"

    data = [
        [data_from_position(pos) for pos in stage_positions]
        for stage_positions in vs.results[1:]
    ]

    data.append([data_from_position(pos, current=True) for pos in vs.positions])

    season, year = vs.name.split()
    season_tl = {
        "summer": "Лето",
        "fall": "Осень",
        "winter": "Зима",
        "spring": "Весна",
    }
    season = season_tl[season.lower()]

    bracket = {
        "title": "{0} {1}".format(season, year),
        "stage": vs.stage,
        "bracket_size": vs.get_bracket_size(),
        "data": data,
    }

    with open(filename, "w", encoding="utf8") as json_file:
        json.dump(bracket, json_file, ensure_ascii=False)


def send_results(vs, bot):
    def format_pair_results(a, b, winner):
        a_name = a.item.get_name()
        b_name = b.item.get_name()
        if winner.seed_number == a.seed_number:
            a_name = f"<b>{a_name}</b> ✅"
        else:
            b_name = f"<b>{b_name}</b> ✅"

        return (
            f"{a.current_votes:02} {a_name}\n     <i>{a.item.get_category()}</i>\n"
            f"{b.current_votes:02} {b_name}\n     <i>{b.item.get_category()}</i>\n"
        )

    prev_results = vs.results[vs.stage - 1]
    current_positions = vs.positions
    text = ""
    if vs.stage == 1:
        separator = "\n\n<b>Вылетели:</b>"
        scores = "\n".join(
            [
                f"{pos.current_votes} {pos.item.get_name()}"
                f"{separator if i == vs.grid_size - 1 else ''}"
                for i, pos in enumerate(prev_results)
            ]
        )
        text += f"<b>Результаты отборочного тура:</b>\n\n{scores}"
    else:
        scores = "\n".join(
            [
                format_pair_results(
                    prev_results[2 * i], prev_results[2 * i + 1], current_positions[i]
                )
                for i in range(vs.grid_size)
            ]
        )
        text += f"<b>Результаты тура:</b>\n\n{scores}"
    kicked_out_chars = {
        (pos.item.get_name(), pos.item.get_category()) for pos in prev_results
    } - {(pos.item.get_name(), pos.item.get_category()) for pos in current_positions}
    kicked_out_titles = {pos.item.get_category() for pos in prev_results} - {
        pos.item.get_category() for pos in current_positions
    }
    if kicked_out_titles:
        kicked_out_text = ""
        for title in kicked_out_titles:
            title_text = f"<b>{title}</b>:\n   "
            title_chars_text = (
                "\n   ".join([char[0] for char in kicked_out_chars if char[1] == title])
                + "\n\n"
            )
            kicked_out_text += title_text + title_chars_text

        text += f"\n\n<b>Вылетевшие тайтлы:</b>\n\n{kicked_out_text}"

    bot.send_message(
        config.dev_tg_id,
        text,
        parse_mode=ParseMode.HTML,
    )
