# tokens
import config
# telegram bot
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler)
# additional utilities
import logging
from pprint import pprint
from datetime import datetime
# my classes
from core import BotCore


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # filename='log/tgbot.log',
                    level=logging.DEBUG)

updater = Updater(token=config.token, use_context=True)
jobs = updater.job_queue
dispatcher = updater.dispatcher

core = BotCore(updater)

job_feeds = jobs.run_repeating(core.jobs.update_nyaa, interval=600, first=0)
announce_time = datetime.strptime("14:01", "%H:%M").time()
job_show_digest = jobs.run_daily(core.jobs.show_daily_events, announce_time)
list_update_time = datetime.strptime("04:30", "%H:%M").time()
job_update_lists = jobs.run_daily(core.jobs.update_lists, list_update_time)

filter_type_dict = {
    'photo': Filters.photo,
    'gif': Filters.document.gif,
    'chat': Filters.chat,
    'unknown': Filters.command,
}

updater.bot.send_message(chat_id=config.dev_tg_id, text='Waking up...')

for category in core.handlers.handlers_list:
    for handler in category.values():
        if 'command' in handler.keys():
            dispatcher.add_handler(CommandHandler(handler['command'], handler['function']))
        elif 'catcher' in handler.keys():
            dispatcher.add_handler(MessageHandler(Filters.chat(chat_id=handler['catcher']), handler['function']))
        elif 'message' in handler.keys():
            dispatcher.add_handler(MessageHandler(filter_type_dict[handler['message']], handler['function']))
        elif 'inline' in handler.keys():
            dispatcher.add_handler(InlineQueryHandler(handler['function']))
        elif 'callback' in handler.keys():
            dispatcher.add_handler(CallbackQueryHandler(handler['function']))
        elif 'error' in handler.keys():
            dispatcher.add_error_handler(handler['function'])

# dispatcher.add_handler(CommandHandler('info', info))
#
# dispatcher.add_handler(CommandHandler(['start', 'help'], start))
#
# dispatcher.add_handler(CommandHandler('seen', users_seen_anime))
# dispatcher.add_handler(CommandHandler('anime', show_anime))
# dispatcher.add_handler(CommandHandler('user_info', show_user_info))
# # dispatcher.add_handler(CommandHandler('manga', show_manga))
#
# dispatcher.add_handler(CommandHandler(['gif_tag', 'tag'], gif_tags))
# dispatcher.add_handler(CommandHandler('set_q', quote_set))
# dispatcher.add_handler(CommandHandler(['what', 'quote'], quotes))
#
# dispatcher.add_handler(InlineQueryHandler(inline_query))
#
# dispatcher.add_handler(CommandHandler('torrents', torrents_stats))
# dispatcher.add_handler(CommandHandler('stats', show_stats))
# dispatcher.add_handler(CommandHandler('lockout', show_lockouts))
# dispatcher.add_handler(CommandHandler('future', show_awaited))
#
# dispatcher.add_handler(MessageHandler(Filters.chat(chat_id=config.main_chat), do_nothing))
#
# dispatcher.add_handler(CommandHandler(['reg', 'register'], register_user))
#
# dispatcher.add_handler(CommandHandler('track', track_anime))
# dispatcher.add_handler(CommandHandler('drop', drop_anime))
#
# dispatcher.add_handler(MessageHandler(Filters.photo, ask_saucenao))
# # todo catch tags in gif caption
# dispatcher.add_handler(MessageHandler(Filters.document.gif, do_nothing))
#
# dispatcher.add_handler(MessageHandler(~ Filters.chat(chat_id=config.dev_tg_id), unauthed))
#
# # echo_handler = MessageHandler(Filters.text, echo)
# # dispatcher.add_handler(echo_handler)
# #
# # caps_handler = CommandHandler('caps', caps)
# # dispatcher.add_handler(caps_handler)
#
# dispatcher.add_handler(CommandHandler('force_deliver', force_deliver))
# dispatcher.add_handler(CommandHandler('send_last', deliver_last))
#
# dispatcher.add_handler(CommandHandler('users', users_stats))
# # dispatcher.add_handler(CommandHandler(['sauce', 'source'], ask_saucenao))
#
# dispatcher.add_handler(CallbackQueryHandler(process_callbacks))
#
# dispatcher.add_handler(MessageHandler(Filters.command, unknown))
#
# dispatcher.add_error_handler(error)

updater.start_polling()
updater.idle()
