import re

from sqlalchemy.exc import IntegrityError

from .exceptions import CharIDNotFoundError, NoLegitAnimeError, AlreadyReleasedError
from handler_modules.base import Handler
from orm.ORMWrapper import SeasonalVotings, Characters, Anime, VotedCharacters


class Nominate(Handler):
    command = "nominate"

    def __init__(self, jikan):
        super().__init__()
        self.jikan = jikan
        self._force = False
        # self.entered = []

    def _get_voting(self):
        session = self.br.get_session()
        result = session.query(SeasonalVotings).filter_by(is_current=True).first()
        # self.entered = session.query(VotedCharacters).filter_by(vid=result.id).all()
        session.close()
        return result

    # todo merge with prep_waifu_list older anime checks
    def _get_char_stats(self, cid, voting):
        session = self.br.get_session()
        char = Characters.get_or_create(cid, session)
        if not char:
            raise CharIDNotFoundError
        if self._force:
            sources = sorted(
                [anime for anime in char.anime],
                key=lambda item: item.popularity,
                reverse=True,
            )
            source = sources[0] if sources else None
        else:
            legit_sources = [
                anime
                for anime in char.anime
                if anime.premiered and anime.premiered.lower() == voting.season
            ]
            # todo OVAs can have no PREMIERED parameter
            blocker_sources = [
                anime
                for anime in char.anime
                if anime.premiered
                and anime.status != "Not yet aired"
                and anime.premiered.lower() != voting.season
                and anime.show_type in ["TV", "OVA", "ONA"]
                and anime.episodes > 3
            ]
            if not legit_sources:
                raise NoLegitAnimeError
            if blocker_sources:
                raise AlreadyReleasedError
            legit_sources.sort(key=lambda item: item.popularity, reverse=True)
            source = legit_sources[0]
        session.close()

        return char.name, source, char.image_url

    def _parse_entry(self, entry, voting):
        cid = name = source = image_url = None
        str_list = entry.split("\n")
        has_cid = re.match(r"https://myanimelist\.net/character/(\d+).*", str_list[0])
        if not has_cid:
            if len(str_list) == 3:
                name, source_title, image_url = tuple(str_list)
                session = self.br.get_session()
                source = session.query(Anime).filter_by(title=source_title).first()
                session.close()
                if not source:
                    return None
        else:
            cid = int(has_cid.group(1))
            try:
                name, source, image_url = self._get_char_stats(cid, voting)
            except (CharIDNotFoundError, NoLegitAnimeError, AlreadyReleasedError):
                return None
            if len(str_list) == 2:
                if re.findall(r"^https?://", str_list[1]):
                    image_url = str_list[1]
        if not (cid or name) or not source:
            return None
        candidate = {
            "vid": voting.id,
            "mal_cid": cid,
            "name": name,
            "image_url": image_url,
            "title": source.title,
            "mal_aid": source.mal_aid,
            # 'anime': source,
        }

        return candidate

    def parse(self, args):
        if args[0] == "force":
            self._force = True
        voting = self._get_voting()
        message = "\n".join(self.message.text.split("\n")[1:])
        entries = message.split("\n\n")
        candidates = []
        unrecognized = []
        for entry in entries:
            candidate = self._parse_entry(entry, voting)
            if candidate:
                candidates.append(candidate)
            else:
                unrecognized.append(entry)

        return candidates, unrecognized

    def process(self, params):
        candidates, unrecognized = params
        session = self.br.get_session()
        duplicates = []
        for candidate in candidates:
            entry = VotedCharacters(**candidate)
            session.add(entry)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                duplicates.append(candidate)

        session.close()
        candidates = [entry for entry in candidates if entry not in duplicates]

        return candidates, unrecognized, duplicates

    def answer(self, result):
        candidates, unrecognized, duplicates = result

        approved = "\n".join(
            [
                f'{char["name"]} - {char["title"]} - {char["image_url"]}'
                for char in candidates
            ]
        )

        text = f"{approved}\n\nUNKNOWN:\n{unrecognized}\n\nDOUBLES:\n{duplicates}"
        self.bot.send_message(chat_id=self.chat.id, text=text)
