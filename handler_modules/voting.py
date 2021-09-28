import re
from collections import defaultdict
from pprint import pprint
from time import sleep
from typing import Tuple

import requests
from sqlalchemy.exc import IntegrityError
from telegram import ParseMode

import config
from orm.ORMWrapper import Anime, Characters, SeasonalVotings, Users, VotedCharacters

from .base import Handler


class VotingCompletedError(Exception):
    pass


class CharIDNotFoundError(Exception):
    pass


class NoLegitAnimeError(Exception):
    pass


class AlreadyReleasedError(Exception):
    pass


class MalformedABParamsError(Exception):
    pass


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
                    voting = self._make_voting(season_str)
                except VotingCompletedError:
                    return f'Голосование за сезон "{season_str}" уже существует!'
                return f'Начато голосование за сезон "{season_str}"'


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


class VotingUpload(Handler):
    command = "voting_upload"

    def parse(self, args):
        id_str, ab_sess, _auth = tuple(args)
        bracket_id = int(id_str)
        if len(ab_sess) != 64 or len(_auth) != 16:
            raise MalformedABParamsError

        return bracket_id, ab_sess, _auth

    def process(self, params):
        bracket_id, ab_sess, _auth = params
        session = self.br.get_session()
        candidates = list(
            session.query(VotedCharacters).filter_by(is_posted=False).all()
        )
        errors = []
        if candidates:
            url = "https://animebracket.com/submit/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 OPR/73.0.3856.284"
            }
            cookies = {
                "AB_SESS": ab_sess,
            }
            params = {"action": "nominate"}
            for entry in candidates:
                data = {
                    "nomineeName": entry.name,
                    "nomineeSource": entry.title,
                    "image": entry.image_url,
                    "bracketId": bracket_id,
                    "_auth": _auth,
                }
                q = requests.post(
                    url, cookies=cookies, headers=headers, data=data, params=params
                )
                if q.text == '{"success":true}':
                    entry.is_posted = True
                elif (
                    q.text
                    == '{"success":false,"message":"You\'re doing that too fast!"}'
                ):
                    sleep(2)
                    candidates.append(entry)
                else:
                    errors.append(f'{entry.name}: "{q.text}"')
                sleep(2)
            session.commit()

        session.close()

        err_text = "\n".join(errors)
        return f"posted everything but:\n\n{err_text}"


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
        msg = f"<b>Список внесённых няш сезона ({waifu_counter})</b>:"
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
