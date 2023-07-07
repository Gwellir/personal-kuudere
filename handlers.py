import inspect
import os
import re
import sys
import traceback
import uuid
from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
from io import BufferedReader, BufferedWriter, BytesIO
from pprint import pprint
from typing import TYPE_CHECKING

from telegram.error import BadRequest

from handler_modules.voting_system.manage_voting import ManageVoting
from handler_modules.voting_system.voting_web_app import VotingWebApp, Vote

# from handler_modules.url_history.url_cache import URLCache

if TYPE_CHECKING:
    from typing import Dict, List, Union

import jikanpy.exceptions
from PIL import Image, UnidentifiedImageError
from saucenao_api import SauceNao
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultCachedMpeg4Gif,
    ParseMode,
    Update,
)
from telegram.utils.helpers import mention_html
from torrentool.torrent import Torrent

import config
from handler_modules.random_anime import AnimeFilter, AnimeSelector
from handler_modules.voting_system.voting import Voting
from handler_modules.voting_system.show_candidates import ShowCandidates
from handler_modules.voting_system.voting_upload import VotingUpload
from handler_modules.voting_system.nominate import Nominate
from utils.expiring_set import ExpiringSet

# todo inline keyboard builder shouldn't be here


def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    pprint(menu)
    return menu


class HandlersList(
    namedtuple(
        "HandlersList",
        [
            "chat",
            # 'private_delim',
            "private",
            # 'admin_delim',
            "admin",
            "chat_join",
            "inline",
            "callbacks",
            "error",
        ],
    )
):
    pass


def detect_unused_handlers(handlers_structure):
    method_list = inspect.getmembers(handlers_structure, predicate=inspect.ismethod)
    func_object_list = set(
        [method[1] for method in method_list if method[0] != "__init__"]
    )
    listed_handlers = []
    for category in handlers_structure.handlers_list:
        for handler in category:
            listed_handlers.append(handler["function"])
    set_of_handlers = set(listed_handlers)
    unused_functions = list(func_object_list - set_of_handlers)
    if unused_functions:
        # raise Exception(f'Unused handlers detected:\n{unused_functions}')
        pprint(unused_functions)


class UtilityFunctions:
    def __init__(self, data_interface, anime_lookup):
        """

        :param data_interface: DataInterface DB connector instance
        :type data_interface: :class:`db_wrapper2.DataInterface`
        """
        self.di = data_interface
        self.al = anime_lookup
        self.relations = {}
        self.build_rel_structure()

    # todo subscription (or delivery) for anime which is unavailable in users' preferred res
    def torrent_subscribe(self, uid, aid):
        PRIORITY_GROUPS = ["SubsPlease", "Erai-raws"]
        group_list = [
            entry[0] for entry in self.di.select_group_list_for_user(aid, uid).all()
        ]
        pprint(group_list)
        if not group_list:
            self.di.insert_new_tracked_title(uid, aid, 0, "SubsPlease")
            return False
        for group in PRIORITY_GROUPS:
            if group in group_list:
                result = group
                self.di.insert_new_tracked_title(uid, aid, 0, group)
                break
        else:
            result = group_list[0]
            self.di.insert_new_tracked_title(uid, aid, 0, result)
        return result

    def torrent_unsubscribe(self, uid, aid):
        self.di.delete_tracked_anime(uid, aid)
        return True

    def get_anime_info(self, query) -> str:
        mal_info = self.al.lookup_anime_info_by_title(query)
        if mal_info:
            anime = self.di.select_anime_by_id(mal_info[0][0]).first()
            output = str(anime)
            if (
                anime.mal_aid in self.relations
                and "chain" in self.relations[anime.mal_aid]
            ):
                franchise = [
                    f'<a href="https://myanimelist.net/anime/{anime_id}">{self.relations[anime_id]["title"]}</a>'
                    if anime_id != anime.mal_aid
                    else f'<b>{self.relations[anime_id]["title"]}</b>'
                    for anime_id in self.relations[anime.mal_aid]["chain"]
                ]
                extension = " ->\n".join(franchise)
                # print(extension)
                output = f"{output}\n\n<b>Timeline:</b>\n{extension}"
        else:
            output = None
        return output

    def build_rel_structure(self):
        """Creates the longest prequel-sequel streaks for all known anime titles.

        Uses Relations JSON data from the DB."""

        starts: List[List[int]] = []
        # подгружаем список тайтлов, id и связей конкретного тайтла
        for entry in self.di.select_relations_data().all():
            # (mal_id, related (JSON), title)
            mal_aid: int
            relations: Dict[str, List[Dict[str, Union[str, int]]]]
            title: str
            mal_aid, relations, title = entry
            self.relations[mal_aid] = {}
            self.relations[mal_aid]["title"] = title

            rel_type: str
            for rel_type in relations:
                self.relations[mal_aid][rel_type] = relations[rel_type]
                # если у тайтла есть сиквел, но не приквел - помещаем в список начал цепочек
                if (
                    rel_type == "Sequel"
                    and ("Prequel" not in relations)
                    and len(relations[rel_type]) > 0
                ):
                    starts.append([mal_aid])

        for chain in starts:
            try:
                # каждое начало цепи (оно гарантированно имеет сиквел)
                next_id = int(self.relations[chain[0]]["Sequel"][0]["mal_id"])
                chain.append(next_id)
            except KeyError as e:
                if type(e.args[0]) == int:
                    self.al.get_anime_by_aid(e.args[0])
                print("ERROR:", e.args)
            i = 1
            try:
                # пока для очередного тайтла в цепочке есть ключ с сиквелами
                while "Sequel" in self.relations[chain[i]]:
                    for seq in self.relations[chain[i]]["Sequel"]:
                        # теоретически очередной сиквел уже может (?) быть в цепи
                        if int(seq["mal_id"]) in chain:
                            continue
                        else:
                            new_id = int(seq["mal_id"])
                            break
                    chain.append(new_id)
                    i += 1
            except KeyError as e:
                print("ERROR:", e.args)
        for chain in starts:
            for anime_id in chain:
                if anime_id not in self.relations:
                    try:
                        self.al.get_anime_by_aid(anime_id)
                    except jikanpy.exceptions.APIException as e:
                        if e.args[0] == 404:
                            # если аниме с соответствующим id не существует, мы обновляем
                            # информацию о его приквеле, чтобы получить актуальный id сиквела
                            self.al.get_anime_by_aid(_previous_id, forced=True)
                            break
                    self.relations[anime_id] = {"title": "Unknown"}
                if "chain" in self.relations[anime_id] and len(
                    self.relations[anime_id]["chain"]
                ) > len(chain):
                    continue
                self.relations[anime_id]["chain"] = chain
                _previous_id = anime_id


class HandlersStructure:
    def __init__(self, updater, jikan, data_interface, list_importer, anime_lookup):
        """
        Initializes requirements for handlers

        :param updater:
        :param jikan:
        :param data_interface: DataInterface DB connector instance
        :type data_interface: :class:`db_wrapper2.DataInterface`
        :type list_importer: :class:`list_parser.ListImporter`
        """
        self.updater = updater
        self.di = data_interface
        self.li = list_importer
        self.jikan = jikan
        self.al = anime_lookup
        self.utilities = UtilityFunctions(data_interface, anime_lookup)
        self.timed_out = ExpiringSet(default_max_age=1800)
        self.handlers_list = HandlersList(
            [
                # these commands can be used in group chats
                {"command": ["info"], "function": self.info},
                {
                    "command": ["start", "help"],
                    "function": self.start,
                    "chats": [config.gacha_chat],
                },
                {"command": ["seen"], "function": self.users_seen_anime},
                {
                    "command": ["anime"],
                    "function": self.show_anime,
                    "chats": [config.gacha_chat],
                },
                {"command": ["user_info"], "function": self.show_user_info},
                {"command": ["gif_tag"], "function": self.gif_tags},
                {"command": ["set_q"], "function": self.quote_set},
                {"command": ["what", "quote"], "function": self.quotes},
                {"command": ["stats"], "function": self.show_stats},
                {"command": ["lockout"], "function": self.show_lockouts},
                {"command": ["future"], "function": self.show_awaited},
                # {'command': ['random'], 'function': self.random_choice},
                {
                    "command": [AnimeSelector.command],
                    "function": AnimeSelector(di=self.di),
                },
                {"command": [AnimeFilter.command], "function": AnimeFilter(di=self.di)},
                {"command": ["users"], "function": self.users_stats},
                {"command": [ShowCandidates.command], "function": ShowCandidates()},
                # {'command': ['source'], 'function': self.ask_saucenao},
                {
                    "message": "sticker",
                    "function": self.convert_webp,
                    "chats": [config.gacha_chat],
                },
                # {
                #     "command": ["admins"],
                #     "function": self.ping_admins,
                #     "chats": [config.gacha_chat],
                #     "no_main": True,
                # },
                # {
                #     "message": "all",
                #     "function": URLCache(),
                #     "group": 1,
                # }
            ],
            [
                # these handlers can be used in private chats with a bot
                {
                    "command": ["reg", "register"],
                    "function": self.register_user,
                    "private": True,
                },
                {"command": ["track"], "function": self.track_anime, "private": True},
                {"command": ["drop"], "function": self.drop_anime, "private": True},
                {
                    "command": ["digest", "today"],
                    "function": self.show_digest,
                    "private": True,
                },
                {
                    "command": ["toggle_torrents", "toggle_delivery"],
                    "function": self.toggle_torrents,
                    "private": True,
                },
                {"message": "photo", "function": self.ask_saucenao, "private": True},
                {
                    "command": ["torrents", "ongoings"],
                    "function": self.torrents_stats,
                    "private": True,
                },
                # this prevents the bot from replying to a gif with unauthed handler
                {"message": "gif", "function": self.do_nothing, "private": True},
            ],
            [
                # admin-only commands
                # 'force_deliver': {'command': ['force_deliver'], 'function': self.force_deliver},
                {
                    "command": ["update_lists"],
                    "function": self.update_lists,
                    "admin": True,
                },
                {
                    "command": ["send_last"],
                    "function": self.deliver_last,
                    "admin": True,
                },
                {
                    "command": ["prep_waifu_list"],
                    "function": self.process_waifus,
                    "admin": True,
                },
                {"command": [Voting.command], "function": Voting(), "admin": True},
                {
                    "command": [Nominate.command],
                    "function": Nominate(self.jikan),
                    "admin": True,
                },
                {
                    "command": [VotingUpload.command],
                    "function": VotingUpload(),
                    "admin": True,
                },
                {
                    "command": [ManageVoting.command],
                    "function": ManageVoting(),
                    "admin": True,
                },
                {
                    "command": [Vote.command],
                    "function": Vote(),
                    "admin": False,
                    "private": True,
                },
                {
                    "message": "web_app_data",
                    "function": VotingWebApp(),
                },
            ],
            [
                # handler for chat join requests
                {"chat_member": "", "function": self.on_chat_join}
            ],
            [
                # handler for inline bot queries
                {"inline": "", "function": self.inline_query}
            ],
            [
                # callback handler
                {"callback": "", "function": self.process_callbacks}
            ],
            [
                # error handler
                {"error": "", "function": self.error}
            ],
        )
        detect_unused_handlers(self)

    def start(self, update, context):
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Бот некоторого аниме-чатика, для регистрации в привате бота введите /reg или /register",
        )

    def info(self, update, context):
        info_post = self.di.select_info_post_from_quotes().first()
        if info_post[1] == "HTML":
            pm = ParseMode.HTML
        elif info_post[1] == "MD":
            pm = ParseMode.MARKDOWN
        else:
            pm = None
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=info_post[0],
            parse_mode=pm,
            disable_web_page_preview=True,
        )

    def quotes(self, update, context):
        q = " ".join(context.args)
        if q:
            q_entry = self.di.select_quotes_by_keyword(q).all()
            if q_entry:
                pm = ParseMode.HTML if q_entry[0][1] == "HTML" else None
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"{q}:\n\n{q_entry[0][0]}",
                    parse_mode=pm,
                )
            else:
                q_entry = self.di.select_quotes_like_keyword(q).all()
                variants = "\n".join(
                    [
                        v[0]
                        for v in sorted(q_entry, key=lambda item: len(item[0][0]))[:5]
                    ]
                )
                msg = f'Не найдено: "{q}"\nПохожие варианты:\n{variants}'
                context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
        else:
            quote_list = [
                f'"{e[0]}"' for e in self.di.select_all_quote_keywords().all()
            ]
            show_limit = 50
            msg = (
                (
                    ", ".join(quote_list[:show_limit])
                    + (
                        f"... (+{len(quote_list) - show_limit})"
                        if len(quote_list) > show_limit
                        else ""
                    )
                    + "\n\n"
                )
                if quote_list
                else ""
            )
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg + "Применение:\n<code>/quote|/what &lt;имя_цитаты&gt;</code>",
                parse_mode=ParseMode.HTML,
            )

    def quote_set(self, update, context):
        q = context.args
        if q:
            uid = update.effective_user.id
            users_id_list = self.di.select_user_tg_ids().all()
            if uid not in [e[0] for e in users_id_list]:
                update.effective_message.reply_text(
                    "Вы не авторизованы для использования цитатника,"
                    " зарегистрируйтесь в моём привате командой /reg."
                )
                return
            params = str.split(update.effective_message.text, " ", 2)
            a = params[2] if len(params) > 2 else None
            name = q[0].replace("_", " ")
            q_list = self.di.select_quote_author_by_keyword(name).first()
            if q_list:
                if q_list[1] != uid:
                    update.effective_message.reply_text(
                        "Этот идентификатор принадлежит чужой цитате!"
                    )
                elif not a:
                    self.di.delete_quotes_by_keyword(name)
                    update.effective_message.reply_text(f'Цитата "{name}" удалена!')
                else:
                    self.di.update_quote_by_keyword(name, a)
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f'Задано:\n"<b>{name}</b>"\n"{a}".',
                        parse_mode=ParseMode.HTML,
                    )
            elif a:
                self.di.insert_new_quote(name, a, None, uid)
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f'Задано:\n"<b>{name}</b>"\n"{a}".',
                    parse_mode=ParseMode.HTML,
                )
            else:
                update.effective_message.reply_text("Цитата не может быть пустой!")
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Применение:\n<code>/set_q &lt;имя_цитаты&gt; &lt;цитата&gt;</code>.",
                parse_mode=ParseMode.HTML,
            )

    def show_stats(self, update, context):
        watched = self.di.select_all_tracked_titles().all()
        total = self.di.select_ongoing_ids().count()
        active_users_count = self.di.select_user_tg_ids().count()
        stats_limit = 15
        watched_str = (
            f"Топ-{stats_limit} отслеживаемых:\n"
            + "\n".join(
                [
                    f'{t[2]:>2}: <a href="https://myanimelist.net/anime/{t[1]}">{t[0]}</a>'
                    for t in watched
                ][:stats_limit]
            )
            + "\n\n"
        )
        msg = (
            (watched_str if watched else "")
            + f"Всего онгоингов отслеживается: {total}.\n"
            f"Зарегистрированных пользователей: {active_users_count}.\n"
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    def users_stats(self, update, context):
        q = context.args
        if len(q) > 0 and q[0] == "season":
            users = "\n".join(
                [u[0] for u in self.di.select_users_with_ongoing_titles_in_list().all()]
            )
            msg = f"Активные пользователи:\n{users}"
        else:
            users = "\n".join(
                [
                    f"{u[1]} - {u[0]}"
                    for u in self.di.select_users_with_any_titles_in_list().all()
                ]
            )
            msg = f"Список пользователей:\n{users}"
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg)

    def torrents_stats(self, update, context):
        all_titles = self.di.select_all_recognized_titles_stats().all()
        count = 0
        size = 50
        while count < len(all_titles):
            msg = f"Список отслеживаемых торрентов:\n" if count == 0 else ""
            torrents = "\n".join(
                [
                    f'<a href="https://myanimelist.net/anime/{t[3]}">{t[0]}</a> ep {t[1]}\n ({t[2]})'
                    for t in all_titles[count : count + size]
                ]
            )
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"{msg}{torrents}",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            count += size

    def show_lockouts(self, update, context):
        lockouts = "\n".join(
            [
                f'<a href="https://myanimelist.net/anime/{t[3]}">{t[0]}</a> ep {t[1]} (до {t[2] + timedelta(hours=24)})'
                for t in self.di.select_locked_out_ongoings().all()
            ]
        )
        msg = (
            f'<b>На данный момент ({datetime.strftime(datetime.now(), "%H:%M")} по Москве)\n'
            f"запрещены спойлеры по</b>:\n\n{lockouts}"
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    def show_awaited(self, update, context):
        q = context.args
        if q:
            name = " ".join(q)
            if len(name) < 3:
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Используйте как минимум три символа для поиска.",
                )
                return
            awaited_s = self.di.select_future_anime_by_producer(name).all()
            studios_str = "\n".join(
                [
                    f'<a href="https://myanimelist.net/anime/{aw[0]}">{aw[1]}</a> ({aw[2]})'
                    + (f" (c {str(aw[3])[:10]})" if aw[3] else "")
                    for aw in awaited_s
                ]
            )
            studios_list = ", ".join(set([aw[4].strip() for aw in awaited_s]))
            awaited_a = list(
                set(
                    [
                        entry[:4]
                        for entry in self.di.select_future_anime_by_title(name).all()
                    ]
                )
            )
            animes_str = "\n".join(
                [
                    f'<a href="https://myanimelist.net/anime/{aw[0]}">{aw[1]}</a> ({aw[2]})'
                    + (f" (c {str(aw[3])[:10]})" if aw[3] else "")
                    for aw in awaited_a
                ]
            )
            if studios_str or animes_str:
                msg = f"<b>Ожидаемые тайтлы</b>:\n"
                if studios_str:
                    msg += f"\nСтудии - {studios_list}:\n" + studios_str + "\n"
                if animes_str:
                    msg += f"\nАниме:\n" + animes_str
            else:
                msg = "По запросу ничего не найдено!"
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id, text="Задайте имя студии или тайтла."
            )

    def show_user_info(self, update, context):
        reply = update.effective_message.reply_to_message
        if reply:
            uid, nick = (
                reply.from_user.id,
                reply.from_user.username
                if reply.from_user.username
                else reply.from_user.full_name,
            )
        else:
            uid, nick = (
                update.effective_user.id,
                update.effective_user.username
                if update.effective_user.username
                else update.effective_user.full_name,
            )

        user_list = self.di.select_user_list_address_by_tg_id(uid).first()
        if not user_list:
            update.effective_message.reply_text(
                f"Cписок пользователя {nick} не зарегистрирован."
            )
            return
        list_prefixes = {
            "MAL": "https://myanimelist.net/animelist/%s",
            "Anilist": "https://anilist.co/user/%s/animelist",
            "Other": "Данные пользователя (%s) загружаются отдельно.",
        }
        list_link = list_prefixes[user_list[1]] % user_list[0]
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Зарегистрированный список пользователя {nick}:\n{list_link}",
        )

    # todo integrate mal search
    # todo add buttons for alt titles
    def users_seen_anime(self, update, context):
        q = " ".join(context.args)
        status_dict = {1: "ong", 2: "done", 3: "hold", 4: "drop", 6: "PTW"}
        titles = None
        if len(q) > 0:
            matches = self.al.lookup_anime_info_by_title(q)
            answer = {
                "chat_id": update.effective_chat.id,
                "parse_mode": ParseMode.HTML,
                "reply_to_message_id": update.effective_message.message_id,
            }
            if matches:
                titles = [(entry[1], entry[0]) for entry in matches]
            if titles:
                msg = (
                    "Найдено аниме:\n"
                    + "\n".join(
                        [
                            f'<a href="https://myanimelist.net/anime/{t[1]}/">{t[0]}</a>'
                            for t in titles[:5]
                        ]
                    )
                    + "\n\n"
                )
                title = titles[0]
                select_seen = self.di.select_user_info_for_seen_title(title[1]).all()
                watched = "\n".join(
                    [
                        f'{item[0]} - {"n/a" if item[1] == 0 else item[1]} '
                        f'({status_dict[item[2]] + (f": {item[3]}" if item[2] != 2 else "")})'
                        for item in select_seen
                        if item[2] != 6
                    ]
                )
                ptw = "\n".join(
                    [
                        f'{item[0]} ({status_dict[item[2]] + (f": {item[3]}" if item[3] != 0 else "")})'
                        for item in select_seen
                        if item[2] == 6
                    ]
                )
                msg += (
                    f"Оценки для тайтла:\n<b>{title[0]}</b>\n\n"
                    + watched
                    + ("\n\n" + ptw if ptw else "")
                )
                answer["text"] = msg
            else:
                answer["text"] = f"Не найдено:\n<b>{q}</b>"

            context.bot.send_message(**answer)

    def process_waifus(self, update, context):
        def waifu_in_anime(id, block_list):
            info = self.jikan.character(id)
            in_anime = [(item["mal_id"], item["name"]) for item in info["animeography"]]
            new_anime = [
                anime
                for anime in in_anime
                if (anime[0] in ongoing_ids) or (anime[0] in movie_ids)
            ]
            old_anime = [
                anime
                for anime in in_anime
                if not (anime[0] in ongoing_ids) and (anime[0] in block_list)
            ]
            return info, new_anime, old_anime

        entities = update.effective_message.parse_entities(types="url")
        if not entities:
            return
        link_list = [*entities.values()]
        mal_character_ids = []
        for link in link_list:
            result = re.match(r"https://myanimelist\\.net/character/(\d+)/.*", link)
            if result:
                mal_character_ids.append(result.group(1))
        mal_character_ids = list(set(mal_character_ids))
        pprint(mal_character_ids)
        ongoing_ids = [item[0] for item in self.di.select_ongoing_ids().all()]
        movie_ids = [item[0] for item in self.di.select_fresh_movie_ids().all()]
        print(ongoing_ids)
        allowed_entries = defaultdict(list)
        waifu_counter = 0
        block_list = [item[0] for item in self.di.select_waifu_blocker_shows().all()]
        for id in mal_character_ids:
            info, new_anime, old_anime = waifu_in_anime(id, block_list)
            if not old_anime:
                allowed_entries[new_anime[0][1]].append((id, info["name"]))
                print(f'ALLOWED: {info["name"]}({id})')
                waifu_counter += 1
            else:
                print(f'DENIED: {info["name"]}({id}) - {old_anime[0][1]}')
        msg = f"<b>Список внесённых няш сезона ({waifu_counter})</b>:"
        # pprint(allowed_entries)
        for anime in [*allowed_entries.keys()]:
            msg += f"\n\n<b>{anime}</b>\n"
            msg += "\n".join(
                [
                    f'<a href="https://myanimelist.net/character/{char[0]}/">{char[1]}</a>'
                    for char in allowed_entries[anime]
                ]
            )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    # todo check whether torrent file still exists
    # todo make sure old callbacks do not fuck shit up
    # todo return more info in case when title part matches more than one title
    def track_anime(self, update, context):
        user = self.di.select_user_entry_by_tg_id(update.effective_user.id).first()
        user_id = user.id
        if not user_id:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Вы не зарегистрированы на боте, используйте /register в моём привате",
            )
            return
        if not context.args:
            tracked = self.di.select_tracked_titles_by_user_tg_id(
                update.effective_user.id
            ).all()
            if tracked:
                if not user.send_torrents:
                    msg = "<b>Вы отказались от получения торрент-файлов!</b>\n"
                else:
                    msg = ""
                tracked.sort(key=lambda item: item[1])
                msg += "Ваши подписки:\n\n" + "\n".join([entry[1] for entry in tracked])
                button_list = [
                    InlineKeyboardButton(
                        f"[{entry[2]}] {entry[1]}",
                        callback_data=f"cg {user_id} {entry[0]} {entry[1][:40]}",
                    )
                    for entry in tracked
                ]
                reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg + "\n\nКнопки ниже управляют выбором группы сабберов.",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
            else:
                msg = "У вас нет подписок!"
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg
                    + "\n\nЧтобы подписаться, используйте:\n/track <части названий через запятую>",
                )
            return
        q = [entry.strip() for entry in " ".join(context.args).split(",")]
        subbed_list = []
        for title in q:
            local_result = self.di.select_anime_to_track_from_ongoings_by_title(
                title
            ).all()
            local_result = sorted(local_result, key=lambda item: len(item[1]))
            if len(local_result) >= 1:
                if not self.di.select_anime_tracked_by_user_id_and_anime_id(
                    user_id, local_result[0][0]
                ).first():
                    group = self.utilities.torrent_subscribe(
                        user_id, local_result[0][0]
                    )
                    subbed_list.append(
                        tuple([local_result[0][0], local_result[0][1], group])
                    )
                else:
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Вы уже отслеживаете {local_result[0][1]}",
                    )
        if subbed_list:
            # subbed_list.sort(key=lambda item: item[1])
            self.deliver_last(update.effective_user.id)
            msg = (
                "Добавлена подписка на аниме:\n\n<b>"
                + "\n".join([x[1] for x in subbed_list])
                + "</b>"
                "\n\nИспользуйте /drop для отмены подписок."
            )
            button_list = [
                InlineKeyboardButton(
                    f"[{entry[2]}] {entry[1]}",
                    callback_data=f"cg {user_id} {entry[0]} {entry[1][:40]}",
                )
                for entry in subbed_list
            ]
            reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="В заданном списке не найдено новых аниме для добавления.",
            )

    def drop_anime(self, update, context):
        q = [entry.strip() for entry in " ".join(context.args).split(",")]
        user = self.di.select_user_entry_by_tg_id(update.effective_user.id).first()
        user_id = user.id
        if not user_id:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Вы не зарегистрированы на боте, используйте /register в моём привате",
            )
            return
        unsubbed_list = []
        for title in q:
            local_result = self.di.select_anime_tracked_by_user_id_and_title(
                user_id, title
            ).all()
            if len(local_result) == 1:
                self.utilities.torrent_unsubscribe(user_id, local_result[0][0])
                unsubbed_list.append(local_result[0])
        if unsubbed_list:
            msg = (
                "Удалена подписка на аниме:\n\n<b>"
                + "\n".join([x[1] for x in unsubbed_list])
                + "</b>"
            )
            context.bot.send_message(
                chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML
            )
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="В заданном списке не найдено аниме из ваших подписок.",
            )

    def toggle_torrents(self, update, context):
        current_status = self.di.switch_torrent_delivery(update.effective_user.id)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Вы включили доставку торрент-файлов."
            if current_status
            else "Вы отключили доставку торрент-файлов.",
        )

    def show_anime(self, update, context):
        if not context.args:
            return
        q = " ".join(context.args)
        output = self.utilities.get_anime_info(q)
        answer = {
            "chat_id": update.effective_chat.id,
            "parse_mode": ParseMode.HTML,
            "reply_to_message_id": update.effective_message.message_id,
        }
        if not output:
            answer["text"] = f'Не найдено: "{q}"'
        else:
            answer["text"] = f"{output}"
        context.bot.send_message(**answer)

    @staticmethod
    def convert_webp(update, context):
        sticker = update.effective_message.sticker
        reply_to = None
        if update.effective_message.reply_to_message:
            reply_to = update.effective_message.reply_to_message.message_id
        if not sticker.emoji:
            filename = f"img/{sticker.file_unique_id}.jpg"
            if not os.path.exists(filename):
                wpo = BytesIO()
                w_write = BufferedWriter(wpo)
                w_read = BufferedReader(wpo)
                file = context.bot.get_file(file_id=sticker.file_id)
                file.download(out=w_write)
                try:
                    img = Image.open(w_read).convert("RGBA")
                except UnidentifiedImageError as e:
                    print(e.args)
                    wpo.close()
                    return
                bg = Image.new("RGBA", img.size, "WHITE")
                bg.paste(img, (0, 0), img)
                bg.convert("RGB").save(filename, "JPEG")
                img.close()
                bg.close()
                wpo.close()
            converted = open(filename, "rb")
            msg = f"WEBP -> JPEG от {update.effective_user.full_name}"
            context.bot.send_photo(
                chat_id=update.effective_chat.id,
                caption=msg,
                photo=converted,
                reply_to_message_id=reply_to,
            )
            context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=update.effective_message.message_id,
            )
            converted.close()

    def ask_saucenao(self, update, context):
        photo_file_id = None
        if update.effective_message.photo:
            photo_file_id = update.effective_message.photo[-1].file_id
        elif update.effective_message.reply_to_message.photo:
            photo_file_id = update.effective_message.reply_to_message.photo[-1].file_id
        if photo_file_id:
            file = context.bot.get_file(file_id=photo_file_id)
            name = f"{str(uuid.uuid4())}.jpg"
            file.download(f"img/{name}")
            saucenao = SauceNao(
                config.saucenao_token,
            )
            filtered_results = saucenao.from_file(open(f"img\\{name}", "rb"))
            pprint(filtered_results)
            sep = "\n"
            results = [
                f"{entry.title}"
                + (f" ({entry.part})" if hasattr(entry, "part") else "")
                + "\n"
                + (
                    f"Est. time: {entry.est_time}\n"
                    if hasattr(entry, "est_time")
                    else ""
                )
                + f"Similarity: {entry.similarity}\n{sep.join(entry.urls)}"
                for entry in filtered_results
                if entry.similarity >= 80
            ]  #
            if not results:
                update.effective_message.reply_text("Похожих изображений не найдено!")
                return
            for res in results:
                msg = f"<b>Найдено:</b>\n" + res
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg,
                    parse_mode=ParseMode.HTML,
                )

    # todo identification by filename and size
    def gif_tags(self, update, context):
        # attach = update.effective_message.document
        # if attach:
        #     has_gif = attach.mime_type == 'video/mp4'
        #     if has_gif:
        #         context.bot.send_message(chat_id=update.effective_chat.id, text=f'Заданы теги:\n{tags}')
        reply = update.effective_message.reply_to_message
        if reply:
            attach = reply.document
            has_gif = attach.mime_type == "video/mp4"
            if has_gif:
                if not context.args:
                    update.effective_message.reply_text("Задайте хотя бы один тег!")
                    return
                q = context.args
                tags = [item.lower().strip() for item in " ".join(q).split(",")]
                former_tags = set(
                    self.di.select_gif_tags_by_media_id(attach.file_id).all()
                )
                v_set = set(
                    [
                        (
                            attach.file_id,
                            tag,
                        )
                        for tag in tags
                    ]
                )
                v_set -= former_tags
                values = tuple(v_set)
                new_tags = [e[1] for e in values]
                old_tags = [e[1] for e in former_tags]
                self.di.insert_tags_into_gif_tags(values)
                msg = (
                    f"Заданы теги: {new_tags}"
                    if new_tags
                    else "Все эти теги уже заданы!"
                )
                msg += f"\nСтарые теги: {old_tags}" if old_tags else ""
                update.effective_message.reply_text(msg)

    def register_user(self, update, context):
        user_name = update.effective_user.username
        user_id = update.effective_user.id
        if user_name:
            this_user = self.di.select_user_data_by_nick(user_name).all()
            if this_user:
                if not this_user[0].tg_id:
                    self.di.update_users_id_for_manually_added_lists(user_id, user_name)
                # else:
                #     context.bot.send_message(chat_id=update.effective_chat.id, text='Вы уже зарегистрированы!')
                #     return
        if (user_id,) not in self.di.select_user_tg_ids().all():
            # print(user_id, self.di.select_user_tg_ids().all())
            self.di.insert_new_user(user_name, user_id)
        msg = (
            "Вы зарегистрированы!\nВыберите предпочитаемое разрешение видео для доставки торрентов (по умолчанию 720р).\n"
            "\nЗатем можете использовать команду /track <набор частей названий через запятую>, "
            "чтобы добавить аниме в список отслеживания"
        )
        res_list = [
            ("1080p HQ", 1080),
            ("720p (умолчание)", 720),
            ("480p LQ или хуже", 480),
        ]
        button_list = [
            InlineKeyboardButton(entry[0], callback_data=f"sr {user_id} {entry[1]}")
            for entry in res_list
        ]
        reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
        context.bot.send_message(
            chat_id=update.effective_chat.id, text=msg, reply_markup=reply_markup
        )

    def ping_admins(self, update, context):
        if update.effective_user.id in self.timed_out:
            return
        self.timed_out.add(update.effective_user.id, custom_max_age=1800)
        try:
            admins = update.effective_chat.get_administrators()
        except BadRequest:
            return
        text = " ".join(
            [
                admin.user.mention_html(
                    f"@{admin.user.username}"
                    if admin.user.username
                    else admin.user.full_name
                )
                for admin in admins
            ]
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    def show_digest(self, update, context):
        user = self.di.select_user_entry_by_tg_id(update.effective_user.id).first()
        user_id = user.id
        if not user_id:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Вы не зарегистрированы на боте, используйте /register в моём привате",
            )
            return
        users_today_titles = self.di.select_today_titles(user_id=user_id)
        daily_list = [
            f'<a href="https://myanimelist.net/anime/{e[2]}">{e[0]}</a> (<i>{e[1]}</i>)'
            for e in users_today_titles
        ]
        if daily_list:
            msg = "#digest\nСегодня ожидаются серии:\n\n" + "\n".join(daily_list)
        else:
            msg = "#digest\nСегодня день отдыха от ониму!"
        self.updater.bot.send_message(
            chat_id=update.effective_user.id,
            text=msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    def on_chat_join(self, update: Update, context):
        event = update.my_chat_member
        context.bot.send_message(
            chat_id=config.dev_tg_id,
            text=f"status change: {event.old_chat_member.status} -> {event.new_chat_member.status}\n"
            f"chat type: {event.chat.type} '{event.chat.title}' with id {event.chat.id}\n"
            f"action by: {event.from_user.link}\n"
            f"member: {event.new_chat_member.user.link}",
            disable_web_page_preview=True,
        )

    def update_lists(self, update, context):
        self.li.update_all()

    def inline_query(self, update, context):
        query = update.inline_query.query
        tag_list = [
            tag.lower().strip()
            for tag in filter(lambda item: item.strip() != "", query.split(","))
        ][:10]
        if tag_list:
            tag_iter = ",".join(["%s" for _ in tag_list])
            tag_list.extend([len(tag_list)])
            # res = self.ani_db.select('media_id', 'gif_tags',
            #                          f'tag IN ({tag_iter}) group by media_id having count(media_id) = %s', tag_list)
            # todo THIS IS NOT FINISHED (but gif tagger isn't working anyway)
            res = self.di.select_gifs_by_tags().all()
            print(res)
            results = [
                InlineQueryResultCachedMpeg4Gif(
                    type="mpeg4_gif", id=uuid.uuid4(), mpeg4_file_id=r[0]
                )
                for r in res
            ]
            # for media in get_media:
            #     if media.media_type == 'animation':
            update.inline_query.answer(results, cache_time=30)

    def process_callbacks(self, update, context):
        q = update.callback_query
        args = q.data.split(" ", 3)
        pprint(args)
        # change group
        if args[0] == "cg":
            # todo think how to pass preferred resolution for user here
            group_list = [
                entry[0]
                for entry in self.di.select_group_list_for_user(args[2], args[1]).all()
            ]
            if group_list:
                button_list = [
                    InlineKeyboardButton(
                        entry, callback_data=f"sg {args[1]} {args[2]} {entry}"
                    )
                    for entry in group_list
                ]
                reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Выберите группу сабберов для:\n{args[3]}",
                    reply_markup=reply_markup,
                )
            else:
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Пока что информация о сабберах отсутствует.",
                )
        # select group
        elif args[0] == "sg":
            self.di.update_group_for_users_release_tracking(args[3], args[1], args[2])
            self.deliver_last(update.effective_user.id)
            q.edit_message_text(
                text=update.effective_message.text + f"\n\nВыбрана группа:\n{args[3]}"
            )
        # select resolution
        elif args[0] == "sr":
            self.di.update_users_preferred_resolution(args[2], args[1])
            q.edit_message_text(
                text=update.effective_message.text
                + f"\n\nВыбрано качество:\n{args[2]}p"
            )

    def unauthed(self, update, context):
        context.bot.send_message(
            chat_id=update.effective_chat.id, text="You're not my master..."
        )

    def do_nothing(self, update, context):
        pass

    def unknown(self, update, context):
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Команда не распознана или предназначена для использования в привате!",
        )

    # this is a general error handler function. If you need more information about specific type of update,
    # add it to the payload in the respective if clause
    def error(self, update, context):
        # add all the dev user_ids in this list. You can also add ids of channels or groups.
        devs = [config.dev_tg_id]
        payload = trace = None
        try:
            # we want to notify the user of this problem. This will always work, but not notify users if the update is an
            # callback or inline query, or a poll update. In case you want this, keep in mind that sending the message
            # could fail
            if update.effective_message:
                text = (
                    "Hey. I'm sorry to inform you that an error happened while I tried to handle your update. "
                    "My developer(s) will be notified."
                )
                update.effective_message.reply_text(text)
            # This traceback is created with accessing the traceback object from the sys.exc_info, which is returned as the
            # third value of the returned tuple. Then we use the traceback.format_tb to get the traceback as a string, which
            # for a weird reason separates the line breaks in a list, but keeps the linebreaks itself. So just joining an
            # empty string works fine.
            trace = "".join(traceback.format_tb(sys.exc_info()[2]))
            # lets try to get as much information from the telegram update as possible
            payload = ""
            # normally, we always have an user. If not, its either a channel or a poll update.
            if update.effective_user:
                payload += f" with the user {mention_html(update.effective_user.id, update.effective_user.first_name)}"
            # there are more situations when you don't get a chat
            if update.effective_chat:
                payload += f" within the chat <i>{update.effective_chat.title}</i>"
                if update.effective_chat.username:
                    payload += f" (@{update.effective_chat.username})"
            # but only one where you have an empty payload by now: A poll (buuuh)
            if update.poll:
                payload += f" with the poll id {update.poll.id}."
        except AttributeError:
            pass
        # lets put this in a "well" formatted text
        text = (
            f"Hey.\n The error <code>{context.error}</code> happened{payload}. The full traceback:\n\n<code>{trace}"
            f"</code>"
        )
        # and send it to the dev(s)
        for dev_id in devs:
            context.bot.send_message(dev_id, text, parse_mode=ParseMode.HTML)
        # we raise the error again, so the logger module catches it. If you don't use the logger module, use it.
        raise

    # def force_deliver(self, update, context):
    #     self.deliver_torrents()

    def deliver_last(self, tg_id):
        entries = self.di.select_last_episodes(tg_id).all()
        for entry in entries:
            try:
                if entry[7]:
                    file = open(entry.torrent, "rb")
                    torrent = Torrent.from_file(entry.torrent)
                    self.updater.bot.send_document(
                        chat_id=entry.tg_id,
                        document=file,
                        caption=f'{entry.torrent.rsplit("/", 1)[1]}\n{torrent.magnet_link}',
                    )
                self.di.update_release_status_for_user_after_delivery(
                    entry.episode, entry.id, entry.mal_aid, entry.a_group
                )
            except FileNotFoundError:
                # todo add redownload logic
                self.updater.bot.send_message(
                    chat_id=entry.tg_id,
                    text=f"NOT FOUND:\n{entry.torrent.rsplit('/', 1)[1]}",
                )
