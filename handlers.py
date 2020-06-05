# config
import os

from jikanpy import APIException

import config
# telegram bot
from telegram import (ParseMode, InlineQueryResultCachedMpeg4Gif, InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.utils.helpers import mention_html
# my classes
from entity_data import AnimeEntry
# service wrappers
from saucenao import SauceNao
# additional utilities
import logging
import sys
import traceback
import uuid
from collections import namedtuple, defaultdict
import inspect
from random import choice as rand_choice
import re
from time import sleep
from pprint import pprint
from datetime import datetime, timedelta
import argparse
from PIL import Image
from io import BufferedWriter, BytesIO, BufferedReader


# todo inline keyboard builder shouldn't be here
def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    pprint(menu)
    return menu


class HandlersList(namedtuple('HandlersList',
                              ['chat', 'private_delim', 'private', 'admin_delim', 'admin', 'unknown', 'inline',
                               'callbacks', 'error'])):
    pass


def detect_unused_handlers(handlers_structure):
    method_list = inspect.getmembers(handlers_structure, predicate=inspect.ismethod)
    func_object_list = set([method[1] for method in method_list if method[0] != '__init__'])
    listed_handlers = []
    for category in handlers_structure.handlers_list:
        for handler in category:
            listed_handlers.append(handler['function'])
    set_of_handlers = set(listed_handlers)
    unused_functions = list(func_object_list - set_of_handlers)
    if unused_functions:
        raise Exception(f'Unused handlers detected:\n{unused_functions}')


class UtilityFunctions:
    def __init__(self, jikan, di):
        """

        :param jikan:
        :param di: DataInterface DB connector instance
        :type di: :class:`db_wrapper2.DataInterface`
        """
        self.jikan = jikan
        self.di = di

    # todo subscription (or delivery) for anime which is unavailable in users' preferred res
    def torrent_subscribe(self, uid, aid):
        PRIORITY_GROUPS = ['HorribleSubs', 'Erai-raws']
        group_list = [entry[0] for entry in self.di.select_group_list_for_user(aid, uid).all()]
        pprint(group_list)
        if not group_list:
            self.di.insert_new_tracked_title(uid, aid, 0, 'HorribleSubs')
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

    def store_anime(self, a_entry):
        self.di.upsert_anime_entry(a_entry)

    # todo obsolete used by anime_walker (scrapper)
    def get_anime_by_aid(self, mal_aid):
        local_result = self.di.select_anime_by_id(mal_aid).first()
        if not local_result or not local_result.popularity:
            anime = self.jikan.anime(mal_aid)
            sleep(config.jikan_delay)
            output = AnimeEntry(**anime)
            self.store_anime(output)
        else:
            output = local_result
        return output

    def get_anime_info(self, query):
        mal_info = self.lookup_anime_info_by_title(query)
        if mal_info:
            anime = self.di.select_anime_by_id(mal_info[0][0]).first()
            # todo it kinda seems that I'm retarded...
            output = AnimeEntry(title=anime.title, type=anime.show_type, status=anime.status, episodes=anime.eps,
                aired={'from': str(anime.started_at), 'to': str(anime.ended_at)}, score=anime.score, image_url=anime.img_url,
                synopsis=anime.synopsis, url=f'https://myanimelist.net/anime/{anime.mal_aid}', airing=None, background=None,
                broadcast=None, duration=None, ending_themes=None, favorites=None, genres=None, headers=None, jikan_url=None,
                licensors=None, mal_id=None, members=None, opening_themes=None, popularity=None, premiered=None,
                producers=None, rank=None, rating=None, related=None, request_cache_expiry=None, request_cached=None,
                request_hash=None, scored_by=None, source=None, studios=None, title_english=None, title_japanese=None,
                title_synonyms=None, trailer_url=None)
        else:
            output = None
        return output

    # todo add streamlined search in cached base
    def lookup_anime_info_by_title(self, a_title, ongoing=False):
        mal_info = self.di.select_anime_info_by_exact_synonym(a_title)
        if not mal_info:
            mal_info = self.di.select_anime_info_by_synonym_part(a_title)
        if not mal_info:
            mal_info = self.di.select_anime_info_by_ordered_token_regex(a_title)
        if not mal_info:
            print(f'Looking up "{a_title}" on MAL...')
            if ongoing:
                try:
                    search_results = self.jikan.search('anime', a_title, page=1,
                                                       parameters={'type': 'tv', 'status': 'airing', 'limit': 5,
                                                                   'genre': 15,
                                                                   'genre_exclude': 0})
                except APIException:
                    return None
            else:
                try:
                    search_results = self.jikan.search('anime', a_title, page=1,
                                                       parameters={'limit': 5})
                except APIException:
                    return None
            sleep(config.jikan_delay)

            mal_info = [(result['mal_id'], result['title'], result['airing'], result['type'], result['members'])
                        for result in search_results['results']]
        else:
            mal_info = sorted(mal_info, key=lambda item: len(item[1]), reverse=False)
        if ongoing:
            mal_info = list(filter(lambda entry: entry[2] is True, mal_info))
        return mal_info


class HandlersStructure:
    def __init__(self, updater, jikan, di):
        """
        Initializes requirements for handlers

        :param updater:
        :param jikan:
        :param di: DataInterface DB connector instance
        :type di: :class:`db_wrapper2.DataInterface`
        """
        self.updater = updater
        self.di = di
        self.jikan = jikan
        self.utilities = UtilityFunctions(jikan, di)
        self.handlers_list = HandlersList(
            [
                # these commands can be used in group chats
                {'command': ['info'], 'function': self.info},
                {'command': ['start', 'help'], 'function': self.start},
                {'command': ['seen'], 'function': self.users_seen_anime},
                {'command': ['anime'], 'function': self.show_anime},
                {'command': ['user_info'], 'function': self.show_user_info},
                {'command': ['gif_tag'], 'function': self.gif_tags},
                {'command': ['set_q'], 'function': self.quote_set},
                {'command': ['what', 'quote'], 'function': self.quotes},
                {'command': ['torrents'], 'function': self.torrents_stats},
                {'command': ['stats'], 'function': self.show_stats},
                {'command': ['lockout'], 'function': self.show_lockouts},
                {'command': ['future'], 'function': self.show_awaited},
                {'command': ['random'], 'function': self.random_choice},
                {'command': ['users'], 'function': self.users_stats},
                {'message': 'sticker', 'function': self.convert_webp},
            ],
            [
                # redirects non-groupchat commands in group chats to an empty handler
                {'catcher': config.main_chat, 'function': self.do_nothing},
            ],
            [
                # these handlers can be used in private chats with a bot
                {'command': ['reg', 'register'], 'function': self.register_user},
                {'command': ['track'], 'function': self.track_anime},
                {'command': ['drop'], 'function': self.drop_anime},
                {'message': 'photo', 'function': self.ask_saucenao},
                # this prevents the bot from replying to a gif with unauthed handler
                {'message': 'gif', 'function': self.do_nothing},
            ],
            [
                # replies with "access denied" to restricted commands in non-admin chats
                {'anti_catcher': config.dev_tg_id, 'function': self.unauthed},
            ],
            [
                # admin-only commands
                # 'force_deliver': {'command': ['force_deliver'], 'function': self.force_deliver},
                {'command': ['send_last'], 'function': self.deliver_last},
                {'command': ['prep_waifu_list'], 'function': self.process_waifus},
            ],
            [
                # handler for /commands which weren't recognized
                {'message': 'unknown', 'function': self.unknown}
            ],
            [
                # handler for inline bot queries
                {'inline': '', 'function': self.inline_query}
            ],
            [
                # callback handler
                {'callback': '', 'function': self.process_callbacks}
            ],
            [
                # error handler
                {'error': '', 'function': self.error}
            ],
        )
        detect_unused_handlers(self)

    def start(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="Бот некоторого аниме-чатика, для регистрации в привате бота введите /reg или /register")

    def info(self, update, context):
        info_post = self.di.select_info_post_from_quotes().first()
        if info_post[1] == 'HTML':
            pm = ParseMode.HTML
        elif info_post[1] == 'MD':
            pm = ParseMode.MARKDOWN
        else:
            pm = None
        context.bot.send_message(chat_id=update.effective_chat.id, text=info_post[0], parse_mode=pm,
                                 disable_web_page_preview=True)

    def random_choice(self, update, context):
        def parse_random_command(opts):
            parser = argparse.ArgumentParser(description='Get random anime from stored userlists.')
            group_score = parser.add_argument_group()
            # group_ptw_score.add_argument('-p', '--ptw', action='store_true')
            group_score.add_argument('-s', '--score', nargs='+', type=int)
            parser.add_argument('-u', '--users', nargs='+')
            parser.add_argument('-t', '--type', nargs='+')

            parsed = None
            try:
                parsed = parser.parse_args(opts)
            except:
                pprint(parsed)

            return parsed

        params = parse_random_command(context.args)
        if not context.args:
            user_list = [entry[0] for entry in self.di.select_user_tg_ids().all()]
            if update.effective_user.id not in user_list:
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text='Вы не зарегистрированы на боте, используйте /reg в моём привате!')
                return
            ptw_list = self.di.select_ptw_list_by_user_tg_id(update.effective_user.id).all()
            answer = None
            if ptw_list:
                answer = rand_choice(ptw_list)
            msg = 'Случайное аниме из PTW:\n\n'
            msg += f'<a href="https://myanimelist.net/anime/{answer[1]}">{answer[0]}</a>'\
                if answer else 'в PTW не найдено тайтлов'
        elif params and not params.score:
            mal_nicks = params.users
            ptw_list = self.di.select_ptw_lists_by_usernames(mal_nicks).all()
            answer = None
            if ptw_list:
                answer = rand_choice(ptw_list)
            sep = ', '
            msg = f'Случайное аниме из PTW пользователя "{sep.join(mal_nicks)}":\n\n'
            msg += f'<a href="https://myanimelist.net/anime/{answer[1]}">{answer[0]}</a>' \
                if answer else 'в PTW не найдено тайтлов'
        else:
            pprint(params)
            ignored_list = [str(entry) for entry in [1306893]]  # toiro
            if not params:
                msg = 'Использование:\n<code>/random</code> - случайное аниме из вашего PTW, либо\n' \
                      '<code>/random [-s X [Y]] [-u user1 user2...] [-t type1* type2*...]</code> - ' \
                      'случайная рекомендация с оценкой из интервала X-Y из списков пользователей бота.\n' \
                      '<code>/random [-u user1 user2...] [-t type1* type2*...]</code> - ' \
                      'случайная рекомендация из списков PTW пользователей бота.\n\n' \
                      '<code>*типы - TV, Movie, OVA, ONA, Special, Music, Unknown, Other</code>'
            else:
                if len(params.score) == 1:
                    params.score.append(params.score[0])
                if params.score[0] not in range(1, 11) or params.score[1] not in range(1, 11):
                    msg = 'Оценка должна быть в диапазоне от 1 до 10'
                else:
                    registered_users = [entry[0].lower() for entry in self.di.select_registered_user_nicks().all()]
                    if params.users:
                        legit_users = [user.lower() for user in params.users if user.lower() in registered_users]
                    else:
                        legit_users = [user.lower() for user in registered_users]
                    if params.type:
                        types_lower = [type_.lower() for type_ in params.type]
                    else:
                        types_lower = ['tv', 'ova', 'movie', 'ona', 'special', 'unknown', 'music', 'other']
                    list_by_score = self.di.select_watched_titles_in_score_interval(params.score[0], params.score[1],
                                                                                      ignored_list).all()
                    your_list = [entry[0] for entry in
                                 self.di.select_watched_list_by_user_tg_id(update.effective_user.id).all()]
                    recommended_list = [entry for entry in list_by_score
                                        if entry[2].lower() in legit_users
                                        and entry[3].lower() in types_lower
                                        and entry[1] not in your_list]
                    print(len(recommended_list), 'items remaining')
                    answer = None
                    if recommended_list:
                        answer = rand_choice(recommended_list)
                    sep = ', '
                    msg = f'<b>Случайное аниме из сохранённых списков</b>:\n'
                    msg += f'<b>пользователи</b>: {sep.join(legit_users)}\n' if params.users else ''
                    msg += f'<b>тип</b>: {sep.join(types_lower)}\n' if params.type else ''
                    msg += f'<b>оценка</b>: [{params.score[0]}-{params.score[1]}]\n\n' if params.score[0] != params.score[1]\
                        else f'<b>оценка</b>: [{params.score[0]}]\n\n'
                    msg += f'<a href="https://myanimelist.net/anime/{answer[1]}">{answer[0]}</a> ({answer[3]}) - {answer[2]}'\
                        if answer else 'в списках не найдено подходящих тайтлов'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)

    def quotes(self, update, context):
        q = ' '.join(context.args)
        if q:
            q_entry = self.di.select_quotes_by_keyword(q).all()
            if q_entry:
                pm = ParseMode.HTML if q_entry[0][1] == 'HTML' else None
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f'{q}:\n\n{q_entry[0][0]}', parse_mode=pm)
            else:
                q_entry = self.di.select_quotes_like_keyword(q).all()
                variants = '\n'.join([v[0] for v in sorted(q_entry, key=lambda item: len(item[0][0]))[:5]])
                msg = f'Не найдено: "{q}"\nПохожие варианты:\n{variants}'
                context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
        else:
            quote_list = [f'"{e[0]}"' for e in self.di.select_all_quote_keywords().all()]
            show_limit = 50
            msg = (', '.join(quote_list[:show_limit]) +
                   (f'... (+{len(quote_list) - show_limit})' if len(quote_list) > show_limit else '') + '\n\n') \
                if quote_list else ''
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=msg + 'Применение:\n<code>/quote|/what &lt;имя_цитаты&gt;</code>',
                                     parse_mode=ParseMode.HTML)

    def quote_set(self, update, context):
        q = context.args
        if q:
            uid = update.effective_user.id
            users_id_list = self.di.select_user_tg_ids().all()
            if uid not in [e[0] for e in users_id_list]:
                update.effective_message.reply_text("Вы не авторизованы для использования цитатника,"
                                                    " зарегистрируйтесь в моём привате командой /reg.")
                return
            params = str.split(update.effective_message.text, ' ', 2)
            a = params[2] if len(params) > 2 else None
            name = q[0].replace("_", " ")
            q_list = self.di.select_quote_author_by_keyword(name).first()
            if q_list:
                if q_list[1] != uid:
                    update.effective_message.reply_text("Этот идентификатор принадлежит чужой цитате!")
                elif not a:
                    self.di.delete_quotes_by_keyword(name)
                    update.effective_message.reply_text(f'Цитата "{name}" удалена!')
                else:
                    self.di.update_quote_by_keyword(name, a)
                    context.bot.send_message(chat_id=update.effective_chat.id,
                                             text=f'Задано:\n"<b>{name}</b>"\n"{a}".', parse_mode=ParseMode.HTML)
            elif a:
                self.di.insert_new_quote(name, a, None, uid)
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f'Задано:\n"<b>{name}</b>"\n"{a}".', parse_mode=ParseMode.HTML)
            else:
                update.effective_message.reply_text("Цитата не может быть пустой!")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=f'Применение:\n<code>/set_q &lt;имя_цитаты&gt; &lt;цитата&gt;</code>.',
                                     parse_mode=ParseMode.HTML)

    def show_stats(self, update, context):
        watched = self.di.select_all_tracked_titles().all()
        total = self.di.select_ongoing_ids().count()
        active_users_count = self.di.select_user_tg_ids().count()
        stats_limit = 15
        watched_str = f'Топ-{stats_limit} отслеживаемых:\n' + \
                      '\n'.join([f'{t[2]:>2}: <a href="https://myanimelist.net/anime/{t[1]}">{t[0]}</a>'
                                 for t in watched][:stats_limit]) + '\n\n'
        msg = (watched_str if watched else '') + f'Всего онгоингов отслеживается: {total}.\n' \
                                                 f'Зарегистрированных пользователей: {active_users_count}.\n'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True)

    def users_stats(self, update, context):
        q = context.args
        if len(q) > 0 and q[0] == 'season':
            users = '\n'.join([u[0] for u in
                               self.di.select_users_with_ongoing_titles_in_list().all()])
            msg = f'Активные пользователи:\n{users}'
        else:
            users = '\n'.join([f'{u[1]} - {u[0]}' for u in
                               self.di.select_users_with_any_titles_in_list().all()])
            msg = f'Список пользователей:\n{users}'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg)

    def torrents_stats(self, update, context):
        torrents = '\n'.join([f'<a href="https://myanimelist.net/anime/{t[3]}">{t[0]}</a> ep {t[1]}\n ({t[2]})'
                              for t in self.di.select_all_recognized_titles_stats().all()
                              ])
        # print(torrents)
        msg = f'Список отслеживаемых торрентов:\n{torrents}'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True)

    def show_lockouts(self, update, context):
        lockouts = '\n'.join([f'<a href="https://myanimelist.net/anime/{t[3]}">'
                              f'{t[0]}</a> ep {t[1]} (до {t[2] + timedelta(hours=24)})'
                              for t in
                              self.di.select_locked_out_ongoings().all()
                              ])
        msg = f'<b>На данный момент ({datetime.strftime(datetime.now(), "%H:%M")} по Москве)\n' \
              f'запрещены спойлеры по</b>:\n\n{lockouts}'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True)

    # todo split into MVC model
    def show_awaited(self, update, context):
        q = context.args
        if q:
            name = ' '.join(q)
            if len(name) < 3:
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text='Используйте как минимум три символа для поиска.')
                return
            awaited_s = self.di.select_future_anime_by_producer(name).all()
            studios_str = '\n'.join([f'<a href="https://myanimelist.net/anime/{aw[0]}">{aw[1]}</a> ({aw[2]})' +
                                     (f' (c {str(aw[3])[:10]})' if aw[3] else '')
                                     for aw in awaited_s])
            studios_list = ', '.join(set([aw[4].strip() for aw in awaited_s]))
            awaited_a = self.di.select_future_anime_by_title(name).all()
            animes_str = '\n'.join([f'<a href="https://myanimelist.net/anime/{aw[0]}">{aw[1]}</a> ({aw[2]})' +
                                    (f' (c {str(aw[3])[:10]})' if aw[3] else '')
                                    for aw in awaited_a])
            if studios_str or animes_str:
                msg = f'<b>Ожидаемые тайтлы</b>:\n'
                if studios_str:
                    msg += f'\nСтудии - {studios_list}:\n' + studios_str + '\n'
                if animes_str:
                    msg += f'\nАниме:\n' + animes_str
            else:
                msg = 'По запросу ничего не найдено!'
            context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                     disable_web_page_preview=True)
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text='Задайте имя студии или тайтла.')

    def show_user_info(self, update, context):
        reply = update.effective_message.reply_to_message
        if reply:
            uid, nick = reply.from_user.id, \
                        reply.from_user.username if reply.from_user.username else reply.from_user.full_name
        else:
            uid, nick = update.effective_user.id, \
                        update.effective_user.username if update.effective_user.username else update.effective_user.full_name

        user_list = self.di.select_user_list_address_by_tg_id(uid).first()
        if not user_list:
            update.effective_message.reply_text(f'Cписок пользователя {nick} не зарегистрирован.')
            return
        list_prefixes = {
            'MAL': 'https://myanimelist.net/animelist/%s',
            'Anilist': 'https://anilist.co/user/%s/animelist'
        }
        list_link = list_prefixes[user_list[1]] % user_list[0]
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=f'Зарегистрированный список пользователя {nick}:\n{list_link}')

    # todo integrate mal search
    # todo add buttons for alt titles
    def users_seen_anime(self, update, context):
        q = ' '.join(context.args)
        status_dict = {
            1: 'ong',
            2: 'done',
            3: 'hold',
            4: 'drop',
            6: 'PTW'
        }
        titles = None
        if len(q) > 0:
            matches = self.utilities.lookup_anime_info_by_title(q)
            if matches:
                titles = [(entry[1], entry[0]) for entry in matches]
            if titles:
                msg = 'Найдено аниме:\n' + \
                      '\n'.join([f'<a href="https://myanimelist.net/anime/{t[1]}/">{t[0]}</a>'
                                 for t in titles[:5]]) + '\n\n'
                title = titles[0]
                select_seen = self.di.select_user_info_for_seen_title(title[1]).all()
                watched = '\n'.join([f'{item[0]} - {"n/a" if item[1] == 0 else item[1]} '
                                     f'({status_dict[item[2]] + (f": {item[3]}" if item[2] != 2 else "")})'
                                     for item in select_seen if item[2] != 6])
                ptw = '\n'.join([f'{item[0]} ({status_dict[item[2]]})' for item in select_seen if item[2] == 6])
                msg += f'Оценки для тайтла:\n<b>{title[0]}</b>\n\n' + watched + ('\n\n' + ptw if ptw else '')
                context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)
            else:
                context.bot.send_message(chat_id=update.effective_chat.id, text=f'Не найдено:\n<b>{q}</b>',
                                         parse_mode=ParseMode.HTML)

    def process_waifus(self, update, context):
        entities = update.effective_message.parse_entities(types='url')
        if not entities:
            return
        link_list = [*entities.values()]
        mal_character_ids = []
        for link in link_list:
            result = re.match('https://myanimelist\\.net/character/(\d+)/.*', link)
            if result:
                mal_character_ids.append(result.group(1))
        pprint(mal_character_ids)
        ongoing_ids = [item[0] for item in
                       self.di.select_ongoing_ids().all()]
        print(ongoing_ids)
        allowed_entries = defaultdict(list)
        waifu_counter = 0
        for id in mal_character_ids:
            info = self.jikan.character(id)
            sleep(config.jikan_delay)
            in_anime = [(item['mal_id'], item['name']) for item in info['animeography']]
            old_anime = [anime for anime in in_anime if not (anime[0] in ongoing_ids)]
            if not old_anime:
                allowed_entries[in_anime[0][1]].append((id, info['name']))
                print(f'ALLOWED: {info["name"]}({id})')
                waifu_counter += 1
            else:
                print(f'DENIED: {info["name"]}({id}) - {old_anime[0][1]}')
        msg = f'<b>Список внесённых няш сезона ({waifu_counter})</b>:'
        # pprint(allowed_entries)
        for anime in [*allowed_entries.keys()]:
            msg += f'\n\n<b>{anime}</b>\n'
            msg += '\n'.join([f'<a href="https://myanimelist.net/character/{char[0]}/">{char[1]}</a>'
                             for char in allowed_entries[anime]])
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True)

    # todo check whether torrent file still exists
    # todo make sure old callbacks do not fuck shit up
    # todo return more info in case when title part matches more than one title
    def track_anime(self, update, context):
        user_id = self.di.select_user_id_by_tg_id(update.effective_user.id).first()
        if not user_id:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text='Вы не зарегистрированы на боте, используйте /register в моём привате')
            return
        else:
            user_id = user_id[0]
        if not context.args:
            tracked = self.di.select_tracked_titles_by_user_tg_id(update.effective_user.id).all()
            if tracked:
                tracked.sort(key=lambda item: item[1])
                msg = 'Ваши подписки:\n\n' + '\n'.join([entry[1] for entry in tracked])
                button_list = [InlineKeyboardButton(f'[{entry[2]}] {entry[1]}',
                                                    callback_data=f"cg {user_id} {entry[0]} {entry[1][:40]}")
                               for entry in tracked]
                reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=msg + '\n\nКнопки ниже управляют выбором группы сабберов.',
                                         reply_markup=reply_markup)
            else:
                msg = 'У вас нет подписок!'
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=msg + '\n\nЧтобы подписаться, используйте:\n/track <части названий через запятую>')
            return
        q = [entry.strip() for entry in ' '.join(context.args).split(',')]
        subbed_list = []
        for title in q:
            local_result = self.di.select_anime_to_track_from_ongoings_by_title(title).all()
            local_result = sorted(local_result, key=lambda item: len(item[1]))
            if len(local_result) >= 1:
                if not self.di.select_anime_tracked_by_user_id_and_anime_id(user_id, local_result[0][0]).first():
                    group = self.utilities.torrent_subscribe(user_id, local_result[0][0])
                    subbed_list.append(tuple([local_result[0][0], local_result[0][1], group]))
                else:
                    context.bot.send_message(chat_id=update.effective_chat.id,
                                             text=f'Вы уже отслеживаете {local_result[0][1]}')
        if subbed_list:
            # subbed_list.sort(key=lambda item: item[1])
            self.deliver_last(update.effective_user.id)
            msg = 'Добавлена подписка на аниме:\n\n<b>' + '\n'.join([x[1] for x in subbed_list]) + '</b>' \
                                                                                                   '\n\nИспользуйте /drop для отмены подписок.'
            button_list = [InlineKeyboardButton(f'[{entry[2]}] {entry[1]}',
                                                callback_data=f"cg {user_id} {entry[0]} {entry[1][:40]}")
                           for entry in subbed_list]
            reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
            context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                     reply_markup=reply_markup)
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text='В заданном списке не найдено новых аниме для добавления.')

    def drop_anime(self, update, context):
        q = [entry.strip() for entry in ' '.join(context.args).split(',')]
        user_id = self.di.select_user_id_by_tg_id(update.effective_user.id).first()
        if not user_id:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text='Вы не зарегистрированы на боте, используйте /register в моём привате')
            return
        user_id = user_id.id
        unsubbed_list = []
        for title in q:
            local_result = self.di.select_anime_tracked_by_user_id_and_title(user_id, title).all()
            if len(local_result) == 1:
                self.utilities.torrent_unsubscribe(user_id, local_result[0][0])
                unsubbed_list.append(local_result[0])
        if unsubbed_list:
            msg = 'Удалена подписка на аниме:\n\n<b>' + '\n'.join([x[1] for x in unsubbed_list]) + '</b>'
            context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text='В заданном списке не найдено аниме из ваших подписок.')

    # TODO implement work with db
    def show_anime(self, update, context):
        if not context.args:
            return
        q = ' '.join(context.args)
        output = self.utilities.get_anime_info(q)
        context.bot.send_message(chat_id=update.effective_chat.id, text=f'{output}',
                                 parse_mode=ParseMode.HTML)
        sleep(config.jikan_delay)

    @staticmethod
    def convert_webp(update, context):
        sticker = update.effective_message.sticker
        if not sticker.emoji:
            filename = f"img/{sticker.file_unique_id}.png"
            if not os.path.exists(filename):
                wpo = BytesIO()
                w_write = BufferedWriter(wpo)
                w_read = BufferedReader(wpo)
                file = context.bot.get_file(file_id=sticker.file_id)
                file.download(out=w_write)
                img = Image.open(w_read).convert("RGBA")
                bg = Image.new("RGBA", img.size, "WHITE")
                bg.paste(img, (0, 0), img)
                bg.convert('RGB').save(filename, "JPEG")
                img.close()
                bg.close()
                wpo.close()
            converted = open(filename, 'rb')
            msg = f'WEBP -> JPEG от {update.effective_user.full_name} ({update.effective_user.username})'
            context.bot.send_photo(chat_id=update.effective_chat.id, caption=msg, photo=converted)
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.effective_message.message_id)
            converted.close()

    def ask_saucenao(self, update, context):
        photo_file_id = update.effective_message.photo[-1].file_id
        if photo_file_id:
            file = context.bot.get_file(file_id=photo_file_id)
            name = f'{str(uuid.uuid4())}.jpg'
            file.download(f'img/{name}')
            saucenao = SauceNao(directory='img', databases=999, minimum_similarity=65, combine_api_types=False,
                                api_key=config.saucenao_token, is_premium=False, exclude_categories='',
                                move_to_categories=False,
                                use_author_as_category=False, output_type=SauceNao.API_HTML_TYPE, start_file='',
                                log_level=logging.ERROR, title_minimum_similarity=90)
            filtered_results = saucenao.check_file(file_name=name)
            pprint(filtered_results)
            sep = '\n'
            results = [f"{entry['data']['title']}\n{sep.join(entry['data']['content'])}\n" +
                       (f"Est. time: {entry['data']['est_time']}\n" if 'est_time' in entry['data'].keys() else '') +
                       f"Similarity: {entry['header']['similarity']}\n{sep.join(entry['data']['ext_urls'])}"
                       for entry in filtered_results if entry['data']['ext_urls']]  #
            if not results:
                update.effective_message.reply_text('Похожих изображений не найдено!')
                return
            for res in results:
                msg = f'<b>Найдено:</b>\n' + res
                context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)

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
            has_gif = attach.mime_type == 'video/mp4'
            if has_gif:
                if not context.args:
                    update.effective_message.reply_text("Задайте хотя бы один тег!")
                    return
                q = context.args
                tags = [item.lower().strip() for item in ' '.join(q).split(',')]
                former_tags = set(self.di.select_gif_tags_by_media_id(attach.file_id).all())
                v_set = set([(attach.file_id, tag,) for tag in tags])
                v_set -= former_tags
                values = tuple(v_set)
                new_tags = [e[1] for e in values]
                old_tags = [e[1] for e in former_tags]
                self.di.insert_tags_into_gif_tags(values)
                msg = f'Заданы теги: {new_tags}' if new_tags else 'Все эти теги уже заданы!'
                msg += f'\nСтарые теги: {old_tags}' if old_tags else ''
                update.effective_message.reply_text(msg)

    def register_user(self, update, context):
        user_name = update.effective_user.username
        user_id = update.effective_user.id
        this_user = self.di.select_user_data_by_nick(user_name).all()
        if this_user:
            if not this_user[0].tg_id:
                self.di.update_users_id_for_manually_added_lists(user_id, user_name)
            # else:
            #     context.bot.send_message(chat_id=update.effective_chat.id, text='Вы уже зарегистрированы!')
            #     return
        else:
            self.di.insert_new_user(user_name, user_id)
        msg = 'Вы зарегистрированы!\nВыберите предпочитаемое разрешение видео для доставки торрентов (по умолчанию 720р).\n' \
              '\nЗатем можете использовать команду /track <набор частей названий через запятую>, ' \
              'чтобы добавить аниме в список отслеживания'
        res_list = [
            ('1080p HQ', 1080),
            ('720p (умолчание)', 720),
            ('480p LQ или хуже', 480)
        ]
        button_list = [InlineKeyboardButton(entry[0], callback_data=f"sr {user_id} {entry[1]}") for entry in res_list]
        reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=reply_markup)

    def inline_query(self, update, context):
        query = update.inline_query.query
        tag_list = [tag.lower().strip() for tag in filter(lambda item: item.strip() != '', query.split(','))][:10]
        if tag_list:
            tag_iter = ','.join(['%s' for _ in tag_list])
            tag_list.extend([len(tag_list)])
            # res = self.ani_db.select('media_id', 'gif_tags',
            #                          f'tag IN ({tag_iter}) group by media_id having count(media_id) = %s', tag_list)
            # todo THIS IS NOT FINISHED (but gif tagger isn't working anyway)
            res = self.di.select_gifs_by_tags().all()
            print(res)
            results = [InlineQueryResultCachedMpeg4Gif(type='mpeg4_gif', id=uuid.uuid4(), mpeg4_file_id=r[0]) for r in
                       res]
            # for media in get_media:
            #     if media.media_type == 'animation':
            update.inline_query.answer(results, cache_time=30)

    def process_callbacks(self, update, context):
        q = update.callback_query
        args = q.data.split(" ", 3)
        pprint(args)
        if args[0] == "cg":
            # todo think how to pass preferred resolution for user here
            group_list = [entry[0] for entry in self.di.select_group_list_for_user(args[2], args[1]).all()]
            if group_list:
                button_list = [InlineKeyboardButton(entry, callback_data=f"sg {args[1]} {args[2]} {entry}")
                               for entry in group_list]
                reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f"Выберите группу сабберов для:\n{args[3]}",
                                         reply_markup=reply_markup)
            else:
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f"Пока что информация о сабберах отсутствует.")
        elif args[0] == "sg":
            self.di.update_group_for_users_release_tracking(args[3], args[1], args[2])
            self.deliver_last(update.effective_user.id)
            q.edit_message_text(text=update.effective_message.text + f"\n\nВыбрана группа:\n{args[3]}")
        elif args[0] == "sr":
            self.di.update_users_preferred_resolution(args[2], args[1])
            q.edit_message_text(text=update.effective_message.text + f"\n\nВыбрано качество:\n{args[2]}p")

    def unauthed(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id, text="You're not my master...")

    def do_nothing(self, update, context):
        pass

    def unknown(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id, text='Sorry, I didn`t understand!')

    # this is a general error handler function. If you need more information about specific type of update,
    # add it to the payload in the respective if clause
    def error(self, update, context):
        # add all the dev user_ids in this list. You can also add ids of channels or groups.
        devs = [config.dev_tg_id]
        # we want to notify the user of this problem. This will always work, but not notify users if the update is an
        # callback or inline query, or a poll update. In case you want this, keep in mind that sending the message
        # could fail
        if update.effective_message:
            text = "Hey. I'm sorry to inform you that an error happened while I tried to handle your update. " \
                   "My developer(s) will be notified."
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
            payload += f' with the user {mention_html(update.effective_user.id, update.effective_user.first_name)}'
        # there are more situations when you don't get a chat
        if update.effective_chat:
            payload += f' within the chat <i>{update.effective_chat.title}</i>'
            if update.effective_chat.username:
                payload += f' (@{update.effective_chat.username})'
        # but only one where you have an empty payload by now: A poll (buuuh)
        if update.poll:
            payload += f' with the poll id {update.poll.id}.'
        # lets put this in a "well" formatted text
        text = f"Hey.\n The error <code>{context.error}</code> happened{payload}. The full traceback:\n\n<code>{trace}" \
               f"</code>"
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
                file = open(entry.torrent, 'rb')
                self.updater.bot.send_document(chat_id=entry.tg_id, document=file,
                                               caption=entry.torrent.rsplit('/', 1)[1])
                self.di.update_release_status_for_user_after_delivery(entry.episode, entry.id, entry.mal_aid, entry.a_group)
            except FileNotFoundError:
                # todo add redownload logic
                self.updater.bot.send_message(chat_id=entry.tg_id, text=f"NOT FOUND:\n{entry.torrent.rsplit('/', 1)[1]}")
