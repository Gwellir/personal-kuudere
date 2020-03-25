# config
import config
# telegram bot
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler)
from telegram import (ParseMode, InlineQueryResultCachedMpeg4Gif, InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.utils.helpers import mention_html
# my classes
from db_wrapper import DBInterface
from entity_data import AnimeEntry
from feed_parser import TorrentFeedParser
from list_parser import ListImporter
# service wrappers
from jikanpy import Jikan
from saucenao import SauceNao
# additional utilities
import logging
import sys
import traceback
import uuid
from collections import namedtuple
import inspect
import re
import html
from time import sleep
from pprint import pprint
from datetime import datetime


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
    def __init__(self, ani_db):
        self.ani_db = ani_db

    # todo subscription (or delivery) for anime which is unavailable in users' preferred res
    def torrent_subscribe(self, uid, aid):
        PRIORITY_GROUPS = ['HorribleSubs', 'Erai-raws']
        group_list = [entry[0] for entry in self.ani_db.select('distinct af.a_group, u.preferred_res',
                                                               'anifeeds af join users u on TRUE',
                                                               'mal_aid = %s and u.preferred_res = af.resolution and u.id = %s',
                                                               [aid, uid])]
        pprint(group_list)
        if not group_list:
            self.ani_db._cursor.execute("insert into users_x_tracked (user_id, mal_aid, last_ep, a_group)"
                                        "values (%s, %s, %s, %s)", (uid, aid, 0, 'HorribleSubs'))
            return False
        # result = False
        for group in PRIORITY_GROUPS:
            if group in group_list:
                result = group
                self.ani_db._cursor.execute("insert into users_x_tracked (user_id, mal_aid, last_ep, a_group)"
                                            "values (%s, %s, %s, %s)", (uid, aid, 0, group))
                break
        else:
            result = group_list[0]
            self.ani_db._cursor.execute("insert into users_x_tracked (user_id, mal_aid, last_ep, a_group)"
                                        "values (%s, %s, %s, %s)", (uid, aid, 0, result))
        self.ani_db.commit()
        return result

    def torrent_unsubscribe(self, uid, aid):
        self.ani_db.delete('users_x_tracked', 'user_id = %s and mal_aid = %s', [uid, aid])
        self.ani_db.commit()
        return True

    def store_anime(self, a_entry):
        local_entry = self.ani_db.select('*', 'anime', 'mal_aid = %s', [a_entry.mal_id])
        if not local_entry:
            self.ani_db._cursor.execute("insert into anime values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                        (a_entry.mal_id, a_entry.title, a_entry.title_english, a_entry.title_japanese,
                                         a_entry.synopsis, a_entry.type,
                                         a_entry.aired['from'][:10] if a_entry.aired['from'] else None,
                                         a_entry.aired['to'][:10] if a_entry.aired['to'] else None,
                                         None, None, a_entry.episodes, a_entry.image_url, a_entry.score, a_entry.status,
                                         ))
            self.ani_db.commit()
        elif local_entry and not local_entry[0][2]:
            self.ani_db.update('anime', "title_eng = %s, title_jap = %s, ended_at = %s, status = %s",
                               [a_entry.title_english, a_entry.title_japanese,
                                a_entry.aired['to'][:10] if a_entry.aired['to'] else None, a_entry.status],
                               'mal_aid = %s', [a_entry.mal_id])
            self.ani_db.commit()


class HandlersStructure:
    def __init__(self, updater, ani_db, jikan):
        self.updater = updater
        self.ani_db = ani_db
        self.jikan = jikan
        self.utilities = UtilityFunctions(ani_db)
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
            ],
            [
                # redirects non-groupchat commands in group chats to an empty function
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
                {'command': ['users'], 'function': self.users_stats},
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
        info_post = self.ani_db.select('content, markdown', 'quotes', 'keyword = %s order by id', ['info'])
        if info_post[0][1] == 'HTML':
            pm = ParseMode.HTML
        elif info_post[0][1] == 'MD':
            pm = ParseMode.MARKDOWN
        else:
            pm = None
        context.bot.send_message(chat_id=update.effective_chat.id, text=info_post[0][0], parse_mode=pm,
                                 disable_web_page_preview=True)

    def quotes(self, update, context):
        q = ' '.join(context.args)
        if q:
            q_entry = self.ani_db.select('content, markdown', 'quotes', 'keyword = %s', [q])
            if q_entry:
                pm = ParseMode.HTML if q_entry[0][1] == 'HTML' else None
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f'{q}:\n\n{q_entry[0][0]}', parse_mode=pm)
            else:
                q_entry = self.ani_db.select('keyword', 'quotes', 'keyword like %s', [f'%{q}%'])
                variants = '\n'.join([v[0] for v in sorted(q_entry, key=lambda item: len(item[0][0]))[:5]])
                msg = f'Не найдено: "{q}"\nПохожие варианты:\n{variants}'
                context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
        else:
            quote_list = [f'"{e[0]}"' for e in self.ani_db.select('keyword', 'quotes order by id')]
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
            if uid not in [e[0] for e in self.ani_db.select('tg_id', 'users', 'tg_id is not %s', [None])]:
                update.effective_message.reply_text("Вы не авторизованы для использования цитатника,"
                                                    " зарегистрируйтесь в моём привате командой /reg.")
                return
            params = str.split(update.effective_message.text, ' ', 2)
            a = params[2] if len(params) > 2 else None
            name = q[0].replace("_", " ")
            q_list = self.ani_db.select('keyword, author_id', 'quotes', 'keyword = %s', [name])
            if q_list:
                if q_list[0][1] != uid:
                    update.effective_message.reply_text("Этот идентификатор принадлежит чужой цитате!")
                elif not a:
                    self.ani_db.delete('quotes', 'keyword = %s', [name])
                    update.effective_message.reply_text(f'Цитата "{name}" удалена!')
                else:
                    self.ani_db.update('quotes', 'content = %s', [a], 'keyword = %s', [name])
                    context.bot.send_message(chat_id=update.effective_chat.id,
                                             text=f'Задано:\n"<b>{name}</b>"\n"{a}".', parse_mode=ParseMode.HTML)
            elif a:
                self.ani_db.add_quote((name, a, None, uid))
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f'Задано:\n"<b>{name}</b>"\n"{a}".', parse_mode=ParseMode.HTML)
            else:
                update.effective_message.reply_text("Цитата не может быть пустой!")
            self.ani_db.commit()
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=f'Применение:\n<code>/set_q &lt;имя_цитаты&gt; &lt;цитата&gt;</code>.',
                                     parse_mode=ParseMode.HTML)

    def show_stats(self, update, context):
        watched = self.ani_db.select('*', 'full_tracking')
        total = self.ani_db.select('count(mal_aid)', 'ongoings')
        active_users_count = self.ani_db.select('count(tg_id)', 'users')
        stats_limit = 15
        watched_str = f'Топ-{stats_limit} отслеживаемых:\n' + \
                      '\n'.join([f'{t[2]:>2}: <a href="https://myanimelist.net/anime/{t[1]}">{t[0]}</a>'
                                 for t in watched][:stats_limit]) + '\n\n'
        msg = (watched_str if watched else '') + f'Всего онгоингов отслеживается: {total[0][0]}.\n' \
                                                 f'Зарегистрированных пользователей: {active_users_count[0][0]}.\n'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True)

    def users_stats(self, update, context):
        q = context.args
        if len(q) > 0 and q[0] == 'season':
            users = '\n'.join([u[0] for u in self.ani_db.select(
                'distinct mal_nick', 'list_status join users on users.mal_uid = list_status.user_id',
                'status = %s and airing = %s and show_type = %s', [1, 1, 'TV'])])
            msg = f'Активные пользователи:\n{users}'
        else:
            users = '\n'.join([u[0] for u in self.ani_db.select('distinct mal_nick',
                                                                'list_status l join users u on u.mal_uid = l.user_id')])
            msg = f'Список пользователей:\n{users}'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg)

    def torrents_stats(self, update, context):
        torrents = '\n'.join([f'<a href="https://myanimelist.net/anime/{t[3]}">{t[0]}</a> ep {t[1]}\n ({t[2]})'
                              for t in self.ani_db.select('distinct a.title, o.last_ep, o.last_release, o.mal_aid',
                                                          'ongoings o left join anime a on a.mal_aid = o.mal_aid '
                                                          'order by a.title')])
        # print(torrents)
        msg = f'Список отслеживаемых торрентов:\n{torrents}'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True)

    def show_lockouts(self, update, context):
        lockouts = '\n'.join([f'<a href="https://myanimelist.net/anime/{t[3]}">{t[0]}</a> ep {t[1]} (до {t[2]})'
                              for t in self.ani_db.select('*', 'lockout')])
        msg = f'<b>Запрещены спойлеры по</b>:\n\n{lockouts}'
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
            awaited_s = self.ani_db.select('*', 'awaited_anime', "name like %s", [f'%{name}%'])[:20]
            studios_str = '\n'.join([f'<a href="https://myanimelist.net/anime/{aw[0]}">{aw[1]}</a> ({aw[2]})' +
                                     (f' (c {str(aw[3])[:10]})' if aw[3] else '')
                                     for aw in awaited_s])
            studios_list = ', '.join(set([aw[4].strip() for aw in awaited_s]))
            awaited_a = self.ani_db.select('*', 'awaited_anime', "title like %s", [f'%{name}%'])[:20]
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

        user_list = self.ani_db.select('mal_nick, service', 'users', 'tg_id = %s', [uid])
        if not user_list:
            update.effective_message.reply_text(f'Cписок пользователя {nick} не зарегистрирован.')
            return
        list_prefixes = {
            'MAL': 'https://myanimelist.net/animelist/%s',
            'Anilist': 'https://anilist.co/user/%s/animelist'
        }
        list_link = list_prefixes[user_list[0][1]] % user_list[0][0]
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
        if len(q) > 0:
            titles = self.ani_db.select('distinct title, mal_aid', 'list_status', 'title like %s', [f'%{q}%'])
            msg = ''
            if titles:
                if len(titles) > 1:
                    titles = sorted(titles, key=lambda item: len(item[0]), reverse=False)
                msg = 'Найдено аниме:\n' + \
                      '\n'.join([f'<a href="https://myanimelist.net/anime/{t[1]}/">{t[0]}</a>'
                                 for t in titles[:5]]) + '\n\n'
                title = titles[0]
                select_seen = self.ani_db.select('u.mal_nick, l.score, l.status, l.watched',
                                                 'list_status l join users u on l.user_id = u.mal_uid',
                                                 'l.mal_aid = %s order by l.score desc', [title[1]])
                watched = '\n'.join([f'{item[0]} - {"n/a" if item[1] == 0 else item[1]} '
                                     f'({status_dict[item[2]] + (f": {item[3]}" if item[2] != 2 else "")})'
                                     for item in select_seen if item[2] != 6])
                ptw = '\n'.join([f'{item[0]} ({status_dict[item[2]]})' for item in select_seen if item[2] == 6])
                msg += f'Оценки для тайтла:\n<b>{title[0]}</b>\n' + watched + ('\n\n' + ptw if ptw else '')
                context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)
                # users_seen = self.ani_db.select()
            else:
                context.bot.send_message(chat_id=update.effective_chat.id, text=f'Не найдено:\n<b>{q}</b>',
                                         parse_mode=ParseMode.HTML)

    # todo check whether torrent file still exists
    # todo make sure old callbacks do not fuck shit up
    def track_anime(self, update, context):
        user_id = self.ani_db.select('id', 'users', 'tg_id = %s', [update.effective_user.id])
        if not user_id:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text='Вы не зарегистрированы на боте, используйте /register в моём привате')
            return
        else:
            user_id = user_id[0][0]
        if not context.args:
            tracked = self.ani_db.select('ut.mal_aid, a.title, ut.a_group',
                                         'users_x_tracked ut join anime a on ut.mal_aid = a.mal_aid '
                                         'join users u on u.id = ut.user_id', 'u.tg_id = %s',
                                         [update.effective_user.id])
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
            local_result = self.ani_db.select("o.mal_aid, a.title", "ongoings o join anime a on a.mal_aid = o.mal_aid",
                                              "a.title like %s and a.show_type in ('TV', 'ONA')", [f'%{title}%'])
            if len(local_result) == 1:
                if not self.ani_db.select('mal_aid', 'users_x_tracked', 'user_id = %s and mal_aid = %s',
                                          [user_id, local_result[0][0]]):
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
        user_id = self.ani_db.select('id', 'users', 'tg_id = %s', [update.effective_user.id])
        if not user_id:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text='Вы не зарегистрированы на боте, используйте /register в моём привате')
            return
        else:
            user_id = user_id[0][0]
        unsubbed_list = []
        for title in q:
            local_result = self.ani_db.select("ut.mal_aid, a.title",
                                              "users_x_tracked ut join anime a on a.mal_aid = ut.mal_aid",
                                              "a.title like %s and a.show_type in ('TV', 'ONA') and ut.user_id = %s",
                                              [f'%{title}%', user_id])
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
        j_result = self.jikan.search('anime', q, parameters={'limit': 5})
        # sleep(2)
        results = j_result['results']
        local_result = None
        # local_result = self.ani_db.select('*', 'anime', 'mal_aid = %s', [results[0]['mal_id']])
        if not local_result:
            anime = self.jikan.anime(results[0]['mal_id'])
        # pprint(anime)
        output = AnimeEntry(**anime)
        self.utilities.store_anime(output)
        context.bot.send_message(chat_id=update.effective_chat.id, text=f'{output}',
                                 parse_mode=ParseMode.HTML)
        sleep(2)

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
            results = [f"{entry['data']['title']}\n{sep.join(entry['data']['content'])}"
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
                former_tags = set(self.ani_db.select('media_id, tag', 'gif_tags', 'media_id = %s', [attach.file_id]))
                v_set = set([(attach.file_id, tag,) for tag in tags])
                v_set -= former_tags
                values = tuple(v_set)
                new_tags = [e[1] for e in values]
                old_tags = [e[1] for e in former_tags]
                self.ani_db._cursor.executemany('insert gif_tags (media_id, tag) VALUES (%s,%s)', values)
                self.ani_db.commit()
                msg = f'Заданы теги: {new_tags}' if new_tags else 'Все эти теги уже заданы!'
                msg += f'\nСтарые теги: {old_tags}' if old_tags else ''
                update.effective_message.reply_text(msg)

    def register_user(self, update, context):
        user_name = update.effective_user.username
        user_id = update.effective_user.id
        this_user = self.ani_db.select('*', 'users', 'tg_nick = %s', [user_name])
        if this_user:
            if not this_user[0][2]:
                self.ani_db.update('users', 'tg_id = %s', [user_id], 'tg_nick = %s', [user_name])
            # else:
            #     context.bot.send_message(chat_id=update.effective_chat.id, text='Вы уже зарегистрированы!')
            #     return
        else:
            self.ani_db._cursor.execute('insert users (tg_nick, tg_id) values (%s, %s)',
                                        [user_name, user_id])
        self.ani_db.commit()
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
            res = self.ani_db.select('media_id', 'gif_tags',
                                     f'tag IN ({tag_iter}) group by media_id having count(media_id) = %s', tag_list)
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
            group_list = [entry[0] for entry in self.ani_db.select('distinct af.a_group, u.preferred_res',
                                                                   'anifeeds af join users u on TRUE',
                                                                   'mal_aid = %s and u.preferred_res = af.resolution and u.id = %s',
                                                                   [args[2], args[1]])]
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
            self.ani_db.update('users_x_tracked', 'a_group = %s, last_ep = %s', [args[3], 0],
                               'user_id = %s and mal_aid = %s', [args[1], args[2]])
            self.ani_db.commit()
            self.deliver_last(update.effective_user.id)
            q.edit_message_text(text=update.effective_message.text + f"\n\nВыбрана группа:\n{args[3]}")
        elif args[0] == "sr":
            self.ani_db.update('users', 'preferred_res = %s', [args[2]], 'tg_id = %s', [args[1]])
            self.ani_db.commit()
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
        entries = self.ani_db.select('*', 'last_episodes', 'tg_id = %s', [tg_id])  # this is a view
        for entry in entries:
            self.updater.bot.send_document(chat_id=entry[0], document=open(entry[1], 'rb'),
                                      caption=entry[1].rsplit('/', 1)[1])
            self.ani_db.update('users_x_tracked', 'last_ep = %s', [entry[2]],
                               'user_id = %s AND mal_aid = %s AND a_group = %s AND last_ep < %s',
                               [entry[4], entry[3], entry[5], entry[2]])
            self.ani_db.commit()
