import config
from telegram import ParseMode


class BotJobs:
    def __init__(self, updater, ani_db, feed_parser, list_importer):
        self.feed_parser = feed_parser
        self.list_importer = list_importer
        self.ani_db = ani_db
        self.updater = updater

    def update_nyaa(self, callback):
        self.feed_parser.check_feeds()
        self.deliver_torrents()
        # Timer(600, update_nyaa).start()

    def show_daily_events(self, callback):
        daily_list = [f'<a href="https://myanimelist.net/anime/{e[2]}">{e[0]}</a> (<i>{e[1]}</i>)'
                      for e in self.ani_db.select('*', 'today_titles')]
        if daily_list:
            msg = '#digest\nСегодня ожидаются серии:\n\n' + '\n'.join(daily_list)
            self.updater.bot.send_message(chat_id=config.main_chat, text=msg, parse_mode=ParseMode.HTML,
                                          disable_web_page_preview=True)

    def update_lists(self, callback):
        self.list_importer.update_all()

    # todo better way of handling episode number update
    # todo now pending_delivery runs on shitty fallback logic, fix ASAP
    def deliver_torrents(self):
        self.ani_db.commit()
        entries = self.ani_db.select('*', 'pending_delivery')  # this is a view
        for entry in entries:
            self.updater.bot.send_document(chat_id=entry[0], document=open(entry[1], 'rb'),
                                           caption=entry[1].rsplit('/', 1)[1])
            self.ani_db.update('users_x_tracked', 'last_ep = %s', [entry[2]],
                               'user_id = %s AND mal_aid = %s AND a_group = %s AND last_ep < %s',
                               [entry[4], entry[3], entry[5], entry[2]])
            self.ani_db.commit()