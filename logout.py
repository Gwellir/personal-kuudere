from telegram.ext import Updater

import config

updater: Updater = Updater(
    token=config.token,
    use_context=True,
    # persistence=PicklePersistence("persist.pickle", store_user_data=False, store_chat_data=False, )
)

updater.dispatcher.bot.log_out()