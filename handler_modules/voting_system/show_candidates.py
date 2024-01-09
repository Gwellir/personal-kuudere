from collections import defaultdict

from telegram import ParseMode

from handler_modules.base import Handler
from orm.ORMWrapper import VotedCharacters, SeasonalVotings, Anime


class ShowCandidates(Handler):
    command = "candidates"

    def process(self, params):
        sess = self.br.get_session()
        entries = (
            sess.query(VotedCharacters)
            .join(SeasonalVotings)
            .join(Anime)
            .filter(SeasonalVotings.is_current == True)
            .all()
        )
        allowed_entries = defaultdict(list)
        waifu_counter = len(entries)
        for char in entries:
            allowed_entries[char.anime.title].append(
                (char.mal_cid, char.name, char.image_url)
            )

        return waifu_counter, allowed_entries

    def answer(self, result):
        waifu_counter, allowed_entries = result
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
