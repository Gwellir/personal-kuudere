# additional utilities
from datetime import datetime

# telegram bot
from telegram.ext import (
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    Filters,
    InlineQueryHandler,
    MessageHandler,
    Updater,
    Dispatcher,
)
from telegram import MessageEntity

# tokens
import config

# my imports
from core import BotCore
from logger.logger import TELEGRAM_LOG

if __name__ == "__main__":

    def get_handler_filters(handler: dict):
        if handler.get("all_chats_allowed", False):
            return
        filters = Filters.chat(config.dev_tg_id)
        if not handler.get("admin", False):
            filters = filters | Filters.chat_type.private
            if not handler.get("private", False):
                chats = handler.get("chats", [])
                if not handler.get("no_main", False):
                    chats.append(config.main_chat)
                filters = filters | Filters.chat(chats)

        return filters

    # telegram.ext initialization
    updater: Updater = Updater(
        token=config.token,
        base_url="http://localhost:8081/bot",
        use_context=True,
        # local_mode=True,
        # persistence=PicklePersistence("persist.pickle", store_user_data=False, store_chat_data=False, )
    )
    dispatcher: Dispatcher = updater.dispatcher
    bot_data = dispatcher.bot_data
    TELEGRAM_LOG.debug(
        f"Init updater and dispatcher for bot: {dispatcher.bot.get_me()}"
    )

    core = BotCore(updater)

    job_queue = updater.job_queue
    # dispatcher.bot_data.update(job_queue=job_queue)
    TELEGRAM_LOG.debug("Init job queue...")

    job_feeds = job_queue.run_repeating(core.jobs.update_nyaa, interval=600, first=10)
    core.jobs.update_continuations(None)
    update_sequels_time = datetime.strptime("06:00 +0300", "%H:%M %z").time()
    job_update_sequels = job_queue.run_daily(
        core.jobs.update_continuations, update_sequels_time
    )
    announce_time = datetime.strptime("14:01 +0300", "%H:%M %z").time()
    job_show_digest = job_queue.run_daily(core.jobs.show_daily_events, announce_time)
    list_update_time = datetime.strptime("04:03 +0300", "%H:%M %z").time()
    job_update_lists = job_queue.run_daily(core.jobs.update_lists, list_update_time)
    seasons_update_time = datetime.strptime("05:03 +0300", "%H:%M %z").time()
    job_update_seasons = job_queue.run_daily(
        core.jobs.update_seasons, seasons_update_time, days=(5,)
    )

    filter_type_dict = {
        "photo": Filters.photo,
        "gif": Filters.document.gif,
        "sticker": Filters.sticker,
        "chat": Filters.chat,
        "url": Filters.entity(MessageEntity.URL),
        "unknown": Filters.command,
        "web_app_data": Filters.status_update.web_app_data,
        "all": Filters.all,
    }

    # feeding handlers for commands and processable message types to dispatcher while applying restrictions
    for category in core.handlers.handlers_list:
        for handler in category:
            if "command" in handler.keys():
                dispatcher.add_handler(
                    CommandHandler(
                        handler["command"],
                        handler["function"],
                        filters=get_handler_filters(handler),
                    ),
                )
            elif "message" in handler.keys():
                dispatcher.add_handler(
                    MessageHandler(
                        filter_type_dict[handler["message"]]
                        & get_handler_filters(handler),
                        handler["function"],
                    ),
                    group=handler.get("group", 0),
                )
            # elif 'regex' in handler.keys():
            #     dispatcher.add_handler(MessageHandler(Filters.regex(handler['regex']), handler['function']))
            elif "chat_member" in handler.keys():
                dispatcher.add_handler(ChatMemberHandler(handler["function"]))
            elif "inline" in handler.keys():
                dispatcher.add_handler(InlineQueryHandler(handler["function"]))
            elif "callback" in handler.keys():
                dispatcher.add_handler(CallbackQueryHandler(handler["function"]))
            elif "error" in handler.keys():
                dispatcher.add_error_handler(handler["function"])

    TELEGRAM_LOG.debug("Init handlers...")

    updater.bot.send_message(chat_id=config.dev_tg_id, text="Waking up...")

    updater.start_polling(
        allowed_updates=[
            "callback_query",
            "chat_join_request",
            "chat_member",
            "channel_post",
            "inline_query",
            "chosen_inline_result",
            "edited_channel_post",
            "edited_message",
            "message",
            "poll",
            "pre_checkout_query",
            "shipping_query",
            "poll_answer",
            "my_chat_member",
        ]
    )
    TELEGRAM_LOG.info("Bot started.")
    updater.idle()
