import json
import logging
from collections import defaultdict

from telegram import ParseMode

import config
from handler_modules.base import Handler
from .create_picture import make_collage
from orm.ORMWrapper import VotedCharacters, SeasonalVotings, Anime


logger = logging.getLogger("handler.show_candidates")


SEASON_NAMES = {
    "winter": "Зима",
    "spring": "Весна",
    "summer": "Лето",
    "fall": "Осень",
}


class ShowCandidates(Handler):
    command = "candidates"

    def process(self, params):
        sess = self.br.get_session()
        entries = (
            sess.query(VotedCharacters)
            .join(SeasonalVotings)
            .join(Anime)
            .filter(SeasonalVotings.is_current == True)
            .with_entities(VotedCharacters.mal_cid, VotedCharacters.name, VotedCharacters.image_url, VotedCharacters.id, Anime.title)
            .all()
        )
        season_id = sess.query(SeasonalVotings).filter(SeasonalVotings.is_current == True).first().season
        season_name = f"{SEASON_NAMES[season_id.split()[0]]} {season_id.split()[1]}"
        logger.debug("Candidates: %s", entries)
        allowed_entries = defaultdict(list)
        waifu_counter = len(entries)
        title_tuples = []
        voting_data = []

        for char in entries:
            allowed_entries[char[4]].append(
                (char[0], char[1], char[2])
            )
            title_tuples.append((char[4], char[3], char[1], char[2]))
            voting_data.append({
                "name": char[1],
                "source": char[4],
                "selected": False,
                "img": f"/img/{char[3]}.jpg"
            })

        image = make_collage(title_tuples, season_name)
        full_data = {
            "candidates": voting_data,
            "title": season_name
        }
        return waifu_counter, image, allowed_entries, full_data

    def answer(self, result):
        waifu_counter, image, allowed_entries, raw_data = result
        msg = f"<b>Список внесённых няш сезона ({waifu_counter})</b> #voting:"
        for anime in [*allowed_entries.keys()]:
            msg += f"\n\n<b>{anime}</b>"
            for char in allowed_entries[anime]:
                link = (
                    f"https://myanimelist.net/character/{char[0]}/"
                    if char[0]
                    else char[2]
                )
                msg += f'\n<a href="{link}">{char[1]}</a>'

        self.bot.send_message(
            chat_id=self.chat.id,
            text=msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        self.bot.send_photo(
            photo=image,
            chat_id=self.chat.id,
        )
        json_data = json.dumps(raw_data) 
        while json_data:
            to_send, json_data = json_data[:4000], json_data[4000:]
            self.bot.send_message(
                chat_id=config.dev_tg_id,
                text=f"<code>{to_send}</code>",
                parse_mode=ParseMode.HTML,
            )
