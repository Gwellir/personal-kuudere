# tokens
import config
# telegram bot
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler)
from telegram import (ParseMode, InlineQueryResultCachedMpeg4Gif, InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.utils.helpers import mention_html
# service wrappers
from jikanpy import Jikan
from saucenao import SauceNao
# additional utilities
import logging
import sys
import traceback
import uuid
import re
import html
from time import sleep
from pprint import pprint
from datetime import datetime
from pytz import timezone
# my classes
from AnimeBotDBWrapper import DBInterface
from AnimeBotEntityData import AnimeEntry
from AnimeBotFeedParser import TorrentFeedParser
from AnimeBotListParser import ListImporter


PRIORITY_GROUPS = ['HorribleSubs', 'Erai-raws']


def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Бот некоторого аниме-чатика, для регистрации в привате бота введите /reg или /register")


def info(update, context):
    info_post = ani_db.select('content, markdown', 'quotes', 'keyword = %s order by id', ['info'])
    if info_post[0][1] == 'HTML':
        pm = ParseMode.HTML
    elif info_post[0][1] == 'MD':
        pm = ParseMode.MARKDOWN
    else:
        pm = None
    context.bot.send_message(chat_id=update.effective_chat.id, text=info_post[0][0], parse_mode=pm,
                             disable_web_page_preview=True)


def quotes(update, context):
    q = ' '.join(context.args)
    if q:
        q_entry = ani_db.select('content, markdown', 'quotes', 'keyword = %s', [q])
        if q_entry:
            pm = ParseMode.HTML if q_entry[0][1] == 'HTML' else None
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=f'{q}:\n\n{q_entry[0][0]}', parse_mode=pm)
        else:
            q_entry = ani_db.select('keyword', 'quotes', 'keyword like %s', [f'%{q}%'])
            variants = '\n'.join([v[0] for v in sorted(q_entry, key=lambda item: len(item[0][0]))[:5]])
            msg = f'Не найдено: "{q}"\nПохожие варианты:\n{variants}'
            context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
    else:
        quote_list = [f'"{e[0]}"' for e in ani_db.select('keyword', 'quotes order by id')]
        show_limit = 50
        msg = (', '.join(quote_list[:show_limit]) +
               (f'... (+{len(quote_list) - show_limit})' if len(quote_list) > show_limit else '') + '\n\n')\
            if quote_list else ''
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=msg + 'Применение:\n<code>/quote|/what &lt;имя_цитаты&gt;</code>',
                                 parse_mode=ParseMode.HTML)


def quote_set(update, context):
    q = context.args
    if q:
        uid = update.effective_user.id
        if uid not in [e[0] for e in ani_db.select('tg_id', 'users', 'tg_id is not %s', [None])]:
            update.effective_message.reply_text("Вы не авторизованы для использования цитатника,"
                                                " зарегистрируйтесь в моём привате командой /reg.")
            return
        params = str.split(update.effective_message.text, ' ', 2)
        a = params[2] if len(params) > 2 else None
        name = q[0].replace("_", " ")
        q_list = ani_db.select('keyword, author_id', 'quotes', 'keyword = %s', [name])
        if q_list:
            if q_list[0][1] != uid:
                update.effective_message.reply_text("Этот идентификатор принадлежит чужой цитате!")
            elif not a:
                ani_db.delete('quotes', 'keyword = %s', [name])
                update.effective_message.reply_text(f'Цитата "{name}" удалена!')
            else:
                ani_db.update('quotes', 'content = %s', [a], 'keyword = %s', [name])
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f'Задано:\n"<b>{name}</b>"\n"{a}".', parse_mode=ParseMode.HTML)
        elif a:
            ani_db.add_quote((name, a, None, uid))
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=f'Задано:\n"<b>{name}</b>"\n"{a}".', parse_mode=ParseMode.HTML)
        else:
            update.effective_message.reply_text("Цитата не может быть пустой!")
        ani_db.commit()
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=f'Применение:\n<code>/set_q &lt;имя_цитаты&gt; &lt;цитата&gt;</code>.',
                                 parse_mode=ParseMode.HTML)


def show_stats(update, context):
    watched = ani_db.select('*', 'full_tracking')
    total = ani_db.select('count(mal_aid)', 'ongoings')
    active_users_count = ani_db.select('count(tg_id)', 'users')
    stats_limit = 15
    watched_str = f'Топ-{stats_limit} отслеживаемых:\n' +\
                  '\n'.join([f'{t[2]:>2}: <a href="https://myanimelist.net/anime/{t[1]}">{t[0]}</a>'
                             for t in watched][:stats_limit]) + '\n\n'
    msg = (watched_str if watched else '') + f'Всего онгоингов отслеживается: {total[0][0]}.\n'\
                                             f'Зарегистрированных пользователей: {active_users_count[0][0]}.\n'
    context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                             disable_web_page_preview=True)


def users_stats(update, context):
    q = context.args
    if len(q) > 0 and q[0] == 'season':
        users = '\n'.join([u[0] for u in ani_db.select(
            'distinct mal_nick', 'list_status join users on users.mal_uid = list_status.user_id',
            'status = %s and airing = %s and show_type = %s', [1, 1, 'TV'])])
        msg = f'Активные пользователи:\n{users}'
    else:
        users = '\n'.join([u[0] for u in ani_db.select('distinct mal_nick',
                                                       'list_status l join users u on u.mal_uid = l.user_id')])
        msg = f'Список пользователей:\n{users}'
    context.bot.send_message(chat_id=update.effective_chat.id, text=msg)


def torrents_stats(update, context):
    torrents = '\n'.join([f'<a href="https://myanimelist.net/anime/{t[3]}">{t[0]}</a> ep {t[1]}\n ({t[2]})'
                          for t in ani_db.select('distinct a.title, o.last_ep, o.last_release, o.mal_aid',
                                                 'ongoings o left join anime a on a.mal_aid = o.mal_aid '
                                                 'order by a.title')])
    # print(torrents)
    msg = f'Список отслеживаемых торрентов:\n{torrents}'
    context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                             disable_web_page_preview=True)


def show_lockouts(update, context):
    lockouts = '\n'.join([f'<a href="https://myanimelist.net/anime/{t[3]}">{t[0]}</a> ep {t[1]} (до {t[2]})'
                          for t in ani_db.select('*', 'lockout')])
    msg = f'<b>Запрещены спойлеры по</b>:\n\n{lockouts}'
    context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                             disable_web_page_preview=True)


def show_user_info(update, context):
    reply = update.effective_message.reply_to_message
    if reply:
        uid, nick = reply.from_user.id,\
                    reply.from_user.username if reply.from_user.username else reply.from_user.first_name
    else:
        uid, nick = update.effective_user.id, update.effective_user.username

    user_list = ani_db.select('mal_nick, service', 'users', 'tg_id = %s', [uid])
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
def users_seen_anime(update, context):
    q = ' '.join(context.args)
    status_dict = {
        1: 'ong',
        2: 'done',
        3: 'hold',
        4: 'drop',
        6: 'PTW'
    }
    if len(q) > 0:
        titles = ani_db.select('distinct title, mal_aid', 'list_status', 'title like %s', [f'%{q}%'])
        msg = ''
        if titles:
            if len(titles) > 1:
                titles = sorted(titles, key=lambda item: len(item[0]), reverse=False)
            msg = 'Найдено аниме:\n' +\
                  '\n'.join([f'<a href="https://myanimelist.net/anime/{t[1]}/">{t[0]}</a>'
                             for t in titles[:5]]) + '\n\n'
            title = titles[0]
            select_seen = ani_db.select('u.mal_nick, l.score, l.status, l.watched',
                                        'list_status l join users u on l.user_id = u.mal_uid',
                                        'l.mal_aid = %s order by l.score desc', [title[1]])
            watched = '\n'.join([f'{item[0]} - {"n/a" if item[1] == 0 else item[1]} '
                                 f'({status_dict[item[2]] + (f": {item[3]}" if item[2] != 2 else "")})'
                                 for item in select_seen if item[2] != 6])
            ptw = '\n'.join([f'{item[0]} ({status_dict[item[2]]})' for item in select_seen if item[2] == 6])
            msg += f'Оценки для тайтла:\n<b>{title[0]}</b>\n' + watched + ('\n\n' + ptw if ptw else '')
            context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)
            # users_seen = ani_db.select()
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text=f'Не найдено:\n<b>{q}</b>',
                                     parse_mode=ParseMode.HTML)


# todo subscription (or delivery) for anime which is unavailable in users' preferred res
def torrent_subscribe(uid, aid):
    group_list = [entry[0] for entry in ani_db.select('distinct af.a_group, u.preferred_res',
                                                      'anifeeds af join users u on TRUE',
                                                      'mal_aid = %s and u.preferred_res = af.resolution and u.id = %s',
                                                      [aid, uid])]
    pprint(group_list)
    if not group_list:
        ani_db._cursor.execute("insert into users_x_tracked (user_id, mal_aid, last_ep, a_group)"
                               "values (%s, %s, %s, %s)", (uid, aid, 0, 'HorribleSubs'))
        return False
    # result = False
    for group in PRIORITY_GROUPS:
        if group in group_list:
            result = group
            ani_db._cursor.execute("insert into users_x_tracked (user_id, mal_aid, last_ep, a_group)"
                                   "values (%s, %s, %s, %s)", (uid, aid, 0, group))
            break
    else:
        result = group_list[0]
        ani_db._cursor.execute("insert into users_x_tracked (user_id, mal_aid, last_ep, a_group)"
                               "values (%s, %s, %s, %s)", (uid, aid, 0, result))
    ani_db.commit()
    return result


def torrent_unsubscribe(uid, aid):
    ani_db.delete('users_x_tracked', 'user_id = %s and mal_aid = %s', [uid, aid])
    ani_db.commit()
    return True


# todo inline keyboard builder shouldn't be here
def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    pprint(menu)
    return menu


# todo make sure old callbacks do not fuck shit up
def track_anime(update, context):
    user_id = ani_db.select('id', 'users', 'tg_id = %s', [update.effective_user.id])
    if not user_id:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text='Вы не зарегистрированы на боте, используйте /register в моём привате')
        return
    else:
        user_id = user_id[0][0]
    if not context.args:
        tracked = ani_db.select('ut.mal_aid, a.title, ut.a_group', 'users_x_tracked ut join anime a on ut.mal_aid = a.mal_aid '
                                'join users u on u.id = ut.user_id', 'u.tg_id = %s', [update.effective_user.id])
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
        local_result = ani_db.select("o.mal_aid, a.title", "ongoings o join anime a on a.mal_aid = o.mal_aid",
                                     "a.title like %s and a.show_type in ('TV', 'ONA')", [f'%{title}%'])
        if len(local_result) == 1:
            if not ani_db.select('mal_aid', 'users_x_tracked', 'user_id = %s and mal_aid = %s',
                                 [user_id, local_result[0][0]]):
                group = torrent_subscribe(user_id, local_result[0][0])
                subbed_list.append(tuple([local_result[0][0], local_result[0][1], group]))
            else:
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text=f'Вы уже отслеживаете {local_result[0][1]}')
    if subbed_list:
        # subbed_list.sort(key=lambda item: item[1])
        deliver_last(update.effective_user.id)
        msg = 'Добавлена подписка на аниме:\n\n<b>' + '\n'.join([x[1] for x in subbed_list]) + '</b>' \
              '\n\nИспользуйте /drop для отмены подписок.'
        button_list = [InlineKeyboardButton(f'[{entry[2]}] {entry[1]}', callback_data=f"cg {user_id} {entry[0]} {entry[1][:40]}")
                       for entry in subbed_list]
        reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML,
                                 reply_markup=reply_markup)
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text='В заданном списке не найдено новых аниме для добавления.')


def drop_anime(update, context):
    q = [entry.strip() for entry in ' '.join(context.args).split(',')]
    user_id = ani_db.select('id', 'users', 'tg_id = %s', [update.effective_user.id])
    if not user_id:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text='Вы не зарегистрированы на боте, используйте /register в моём привате')
        return
    else:
        user_id = user_id[0][0]
    unsubbed_list = []
    for title in q:
        local_result = ani_db.select("ut.mal_aid, a.title", "users_x_tracked ut join anime a on a.mal_aid = ut.mal_aid",
                                     "a.title like %s and a.show_type in ('TV', 'ONA') and ut.user_id = %s",
                                     [f'%{title}%', user_id])
        if len(local_result) == 1:
            torrent_unsubscribe(user_id, local_result[0][0])
            unsubbed_list.append(local_result[0])
    if unsubbed_list:
        msg = 'Удалена подписка на аниме:\n\n<b>' + '\n'.join([x[1] for x in unsubbed_list]) + '</b>'
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text='В заданном списке не найдено аниме из ваших подписок.')


def store_anime(a_entry):
    local_entry = ani_db.select('*', 'anime', 'mal_aid = %s', [a_entry.mal_id])
    if not local_entry:
        ani_db._cursor.execute("insert into anime values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                               (a_entry.mal_id, a_entry.title, a_entry.title_english, a_entry.title_japanese,
                                a_entry.synopsis, a_entry.type,
                                a_entry.aired['from'][:10] if a_entry.aired['from'] else None,
                                a_entry.aired['to'][:10] if a_entry.aired['to'] else None,
                                None, None, a_entry.episodes, a_entry.image_url, a_entry.score, a_entry.status,
                                ))
        ani_db.commit()
    elif local_entry and not local_entry[0][2]:
        ani_db.update('anime', "title_eng = %s, title_jap = %s, ended_at = %s, status = %s",
                      [a_entry.title_english, a_entry.title_japanese,
                       a_entry.aired['to'][:10] if a_entry.aired['to'] else None, a_entry.status],
                      'mal_aid = %s', [a_entry.mal_id])
        ani_db.commit()


# TODO implement work with db
def show_anime(update, context):
    if not context.args:
        return
    q = ' '.join(context.args)
    j_result = jikan.search('anime', q, parameters={'limit': 5})
    # sleep(2)
    results = j_result['results']
    local_result = None
    # local_result = ani_db.select('*', 'anime', 'mal_aid = %s', [results[0]['mal_id']])
    if not local_result:
        anime = jikan.anime(results[0]['mal_id'])
    # pprint(anime)
    output = AnimeEntry(**anime)
    store_anime(output)
    context.bot.send_message(chat_id=update.effective_chat.id, text=f'{output}',
                             parse_mode=ParseMode.HTML)
    sleep(2)


def ask_saucenao(update, context):
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
def gif_tags(update, context):
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
            former_tags = set(ani_db.select('media_id, tag', 'gif_tags', 'media_id = %s', [attach.file_id]))
            v_set = set([(attach.file_id, tag,) for tag in tags])
            v_set -= former_tags
            values = tuple(v_set)
            new_tags = [e[1] for e in values]
            old_tags = [e[1] for e in former_tags]
            ani_db._cursor.executemany('insert gif_tags (media_id, tag) VALUES (%s,%s)', values)
            ani_db.commit()
            msg = f'Заданы теги: {new_tags}' if new_tags else 'Все эти теги уже заданы!'
            msg += f'\nСтарые теги: {old_tags}' if old_tags else ''
            update.effective_message.reply_text(msg)


def register_user(update, context):
    user_name = update.effective_user.username
    user_id = update.effective_user.id
    this_user = ani_db.select('*', 'users', 'tg_nick = %s', [user_name])
    if this_user:
        if not this_user[0][2]:
            ani_db.update('users', 'tg_id = %s', [user_id], 'tg_nick = %s', [user_name])
        # else:
        #     context.bot.send_message(chat_id=update.effective_chat.id, text='Вы уже зарегистрированы!')
        #     return
    else:
        ani_db._cursor.execute('insert users (tg_nick, tg_id) values (%s, %s)',
                               [user_name, user_id])
    ani_db.commit()
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


def inline_query(update, context):
    query = update.inline_query.query
    tag_list = [tag.lower().strip() for tag in filter(lambda item: item.strip() != '', query.split(','))][:10]
    if tag_list:
        tag_iter = ','.join(['%s' for _ in tag_list])
        tag_list.extend([len(tag_list)])
        res = ani_db.select('media_id', 'gif_tags',
                            f'tag IN ({tag_iter}) group by media_id having count(media_id) = %s', tag_list)
        print(res)
        results = [InlineQueryResultCachedMpeg4Gif(type='mpeg4_gif', id=uuid.uuid4(), mpeg4_file_id=r[0]) for r in res]
        # for media in get_media:
        #     if media.media_type == 'animation':
        update.inline_query.answer(results, cache_time=30)


def process_callbacks(update, context):
    q = update.callback_query
    args = q.data.split(" ", 3)
    pprint(args)
    if args[0] == "cg":
        # todo think how to pass preferred resolution for user here
        group_list = [entry[0] for entry in ani_db.select('distinct af.a_group, u.preferred_res',
                                                          'anifeeds af join users u on TRUE',
                                                          'mal_aid = %s and u.preferred_res = af.resolution and u.id = %s',
                                                          [args[2], args[1]])]
        if group_list:
            button_list = [InlineKeyboardButton(entry, callback_data=f"sg {args[1]} {args[2]} {entry}")
                           for entry in group_list]
            reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))
            context.bot.send_message(chat_id=update.effective_chat.id, text=f"Выберите группу сабберов для:\n{args[3]}",
                                     reply_markup=reply_markup)
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=f"Пока что информация о сабберах отсутствует.")
    elif args[0] == "sg":
        ani_db.update('users_x_tracked', 'a_group = %s, last_ep = %s', [args[3], 0],
                      'user_id = %s and mal_aid = %s', [args[1], args[2]])
        ani_db.commit()
        deliver_last(update.effective_user.id)
        q.edit_message_text(text=update.effective_message.text + f"\n\nВыбрана группа:\n{args[3]}")
    elif args[0] == "sr":
        ani_db.update('users', 'preferred_res = %s', [args[2]], 'tg_id = %s', [args[1]])
        ani_db.commit()
        q.edit_message_text(text=update.effective_message.text + f"\n\nВыбрано качество:\n{args[2]}p")


def unauthed(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="You're not my master...")


def do_nothing(update, context):
    pass


def unknown(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text='Sorry, I didn`t understand!')


# this is a general error handler function. If you need more information about specific type of update, add it to the
# payload in the respective if clause
def error(update, context):
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


def update_nyaa(callback):
    feed_parser = TorrentFeedParser()
    feed_parser.check_feeds()
    deliver_torrents()
    # Timer(600, update_nyaa).start()


def show_daily_events(callback):
    daily_list = [f'<a href="https://myanimelist.net/anime/{e[2]}">{e[0]}</a> (<i>{e[1]}</i>)'
                  for e in ani_db.select('*', 'today_titles')]
    if daily_list:
        msg = '#digest\nСегодня ожидаются серии:\n\n' + '\n'.join(daily_list)
        updater.bot.send_message(chat_id=config.main_chat, text=msg, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True)


def update_lists(callback):
    li = ListImporter()
    li.update_all()


def force_deliver(update, context):
    deliver_torrents()


def deliver_last(tg_id):
    entries = ani_db.select('*', 'last_episodes', 'tg_id = %s', [tg_id])  # this is a view
    for entry in entries:
        updater.bot.send_document(chat_id=entry[0], document=open(entry[1], 'rb'),
                                  caption=entry[1].rsplit('/', 1)[1])
        ani_db.update('users_x_tracked', 'last_ep = %s', [entry[2]],
                      'user_id = %s AND mal_aid = %s AND a_group = %s AND last_ep < %s',
                      [entry[4], entry[3], entry[5], entry[2]])
        ani_db.commit()


# todo better way of handling episode number update
# todo now pending_delivery runs on shitty fallback logic, fix ASAP
def deliver_torrents():
    ani_db.commit()
    entries = ani_db.select('*', 'pending_delivery')  # this is a view
    for entry in entries:
        updater.bot.send_document(chat_id=entry[0], document=open(entry[1], 'rb'),
                                  caption=entry[1].rsplit('/', 1)[1])
        ani_db.update('users_x_tracked', 'last_ep = %s', [entry[2]],
                      'user_id = %s AND mal_aid = %s AND a_group = %s AND last_ep < %s',
                      [entry[4], entry[3], entry[5], entry[2]])
        ani_db.commit()


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # filename='log/tgbot.log',
                    level=logging.DEBUG)

ani_db = DBInterface()
jikan = Jikan()

updater = Updater(token=config.token, use_context=True)
jobs = updater.job_queue
dispatcher = updater.dispatcher

job_feeds = jobs.run_repeating(update_nyaa, interval=600, first=0)
announce_time = datetime.strptime("14:01", "%H:%M").time()
job_show_digest = jobs.run_daily(show_daily_events, announce_time)
list_update_time = datetime.strptime("04:30", "%H:%M").time()
job_update_lists = jobs.run_daily(update_lists, list_update_time)


updater.bot.send_message(chat_id=config.dev_tg_id, text='Waking up...')

dispatcher.add_handler(CommandHandler('info', info))

dispatcher.add_handler(CommandHandler(['start', 'help'], start))

dispatcher.add_handler(CommandHandler('seen', users_seen_anime))
dispatcher.add_handler(CommandHandler('anime', show_anime))
dispatcher.add_handler(CommandHandler('user_info', show_user_info))
# dispatcher.add_handler(CommandHandler('manga', show_manga))

dispatcher.add_handler(CommandHandler(['gif_tag', 'tag'], gif_tags))
dispatcher.add_handler(CommandHandler('set_q', quote_set))
dispatcher.add_handler(CommandHandler(['what', 'quote'], quotes))

dispatcher.add_handler(InlineQueryHandler(inline_query))

dispatcher.add_handler(CommandHandler('torrents', torrents_stats))
dispatcher.add_handler(CommandHandler('stats', show_stats))
dispatcher.add_handler(CommandHandler('lockout', show_lockouts))

dispatcher.add_handler(MessageHandler(Filters.chat(chat_id=config.main_chat), do_nothing))

dispatcher.add_handler(CommandHandler(['reg', 'register'], register_user))

dispatcher.add_handler(CommandHandler('track', track_anime))
dispatcher.add_handler(CommandHandler('drop', drop_anime))

dispatcher.add_handler(MessageHandler(Filters.photo, ask_saucenao))
# todo catch tags in gif caption
dispatcher.add_handler(MessageHandler(Filters.document.gif, do_nothing))

dispatcher.add_handler(MessageHandler(~ Filters.chat(chat_id=config.dev_tg_id), unauthed))

# echo_handler = MessageHandler(Filters.text, echo)
# dispatcher.add_handler(echo_handler)
#
# caps_handler = CommandHandler('caps', caps)
# dispatcher.add_handler(caps_handler)

dispatcher.add_handler(CommandHandler('force_deliver', force_deliver))
dispatcher.add_handler(CommandHandler('send_last', deliver_last))

dispatcher.add_handler(CommandHandler('users', users_stats))
# dispatcher.add_handler(CommandHandler(['sauce', 'source'], ask_saucenao))

dispatcher.add_handler(CallbackQueryHandler(process_callbacks))

dispatcher.add_handler(MessageHandler(Filters.command, unknown))

updater.dispatcher.add_error_handler(error)

updater.start_polling()
updater.idle()
