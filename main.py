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


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', #filename='log/tgbot.log',
                    level=logging.DEBUG)

# telegram.ext initialization
updater = Updater(token=config.token, use_context=True)
jobs = updater.job_queue
dispatcher = updater.dispatcher

core = BotCore(updater)

job_feeds = jobs.run_repeating(core.jobs.update_nyaa, interval=600, first=0)
announce_time = datetime.strptime("14:01 +0300", "%H:%M %z").time()
job_show_digest = jobs.run_daily(core.jobs.show_daily_events, announce_time)
list_update_time = datetime.strptime("04:03 +0300", "%H:%M %z").time()
job_update_lists = jobs.run_daily(core.jobs.update_lists, list_update_time)

filter_type_dict = {
    'photo': Filters.photo,
    'gif': Filters.document.gif,
    'sticker': Filters.sticker,
    'chat': Filters.chat,
    'unknown': Filters.command,
}

# feeding handlers for commands and processable message types to dispatcher while applying restrictions
for category in core.handlers.handlers_list:
    for handler in category:
        if 'command' in handler.keys():
            dispatcher.add_handler(CommandHandler(handler['command'], handler['function']))
        elif 'catcher' in handler.keys():
            dispatcher.add_handler(MessageHandler(Filters.chat(chat_id=handler['catcher']), handler['function']))
        elif 'anti_catcher' in handler.keys():
            dispatcher.add_handler(MessageHandler(~ Filters.chat(chat_id=handler['anti_catcher']), handler['function']))
        elif 'message' in handler.keys():
            dispatcher.add_handler(MessageHandler(filter_type_dict[handler['message']], handler['function']))
        elif 'inline' in handler.keys():
            dispatcher.add_handler(InlineQueryHandler(handler['function']))
        elif 'callback' in handler.keys():
            dispatcher.add_handler(CallbackQueryHandler(handler['function']))
        elif 'error' in handler.keys():
            dispatcher.add_error_handler(handler['function'])

updater.bot.send_message(chat_id=config.dev_tg_id, text='Waking up...')


updater.start_polling()
updater.idle()
