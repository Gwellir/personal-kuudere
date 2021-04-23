from telegram import ParseMode
from telegram.error import BadRequest

import config


class BotJobs:
    def __init__(self, updater, feed_parser, list_importer, data_interface):
        """
        Initializes requirements for jobs

        :param data_interface: DataInterface DB connector instance
        :type data_interface: :class:`db_wrapper2.DataInterface`
        :param list_importer: ListImporter instance
        :type list_importer: :class:`list_parser.ListImporter`
        :param synonyms: Synonyms processor instance
        :type synonyms: :class:`anime_synonyms.Synonyms`

        """
        self.feed_parser = feed_parser
        self.li = list_importer
        self.updater = updater
        self.di = data_interface

    def update_nyaa(self, callback):
        self.feed_parser.check_feeds()
        self.deliver_torrents()

    def show_daily_events(self, callback):
        today_titles = self.di.select_today_titles().all()
        daily_list = [
            f'<a href="https://myanimelist.net/anime/{e[2]}">{e[0]}</a> (<i>{e[1]}</i>)'
            for e in today_titles
        ]
        if daily_list:
            msg = "#digest\nСегодня ожидаются серии:\n\n" + "\n".join(daily_list)
            self.updater.bot.send_message(
                chat_id=config.main_chat,
                text=msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    def update_lists(self, callback):
        self.li.update_all()

    # todo better way of handling episode number update
    # todo now pending_delivery runs on shitty fallback logic, fix ASAP
    def deliver_torrents(self):
        entries = self.di.select_titles_pending_for_delivery().all()
        for entry in entries:
            try:
                file = open(entry[1], "rb")
                self.updater.bot.send_document(
                    chat_id=entry[0], document=file, caption=entry[1].rsplit("/", 1)[1]
                )
                self.di.update_release_status_for_user_after_delivery(
                    entry[2], entry[4], entry[3], entry[5]
                )
            except FileNotFoundError:
                # todo add redownload logic
                self.updater.bot.send_message(
                    chat_id=entry[0], text=f"NOT FOUND:\n{entry[1].rsplit('/', 1)[1]}"
                )
            except BadRequest:
                self.updater.bot.send_message(
                    chat_id=config.dev_tg_id, text=f"USER NOT BOUND:\n{entry[0]}"
                )

    def update_seasons(self, callback):
        self.li.update_seasonal()
