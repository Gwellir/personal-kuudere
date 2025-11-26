import re

import requests
from telegram import ParseMode
from telegram.error import BadRequest
from torrentool.api import Torrent

import config
from utils.daily_digest import get_digest


class BotJobs:
    def __init__(
        self, updater, feed_parser, list_importer, data_interface, anime_lookup
    ):
        """
        Initializes requirements for jobs

        :param data_interface: DataInterface DB connector instance
        :type data_interface: :class:`utils.db_wrapper2.DataInterface`
        :param list_importer: ListImporter instance
        :type list_importer: :class:`parsers.list_parser.ListImporter`
        :param synonyms: Synonyms processor instance
        :type synonyms: :class:`utils.anime_synonyms.Synonyms`
        :type anime_lookup: :class:`utils.anime_lookup.AnimeLookup`

        """
        self.feed_parser = feed_parser
        self.li = list_importer
        self.updater = updater
        self.di = data_interface
        self.al = anime_lookup

    def update_nyaa(self, callback):
        self.feed_parser.check_feeds()
        self.deliver_torrents()

    def show_daily_events(self, callback):
        digest = get_digest()
        digest.sort(key=lambda title: title.get("time"))
        daily_list = [
            f'• <a href="https://myanimelist.net/anime/{t["mal_aid"]}">{t["name"]}</a> '
            f'[{t["time"].isoformat(timespec="minutes")}]'
            for t in digest
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
                if entry[7]:
                    file = open(entry[1], "rb")
                    torrent = Torrent.from_file(entry[1])
                    self.updater.bot.send_document(
                        chat_id=entry[0],
                        document=file,
                        caption=f'{entry[1].rsplit("/", 1)[1]}\n{torrent.magnet_link}',
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

    def update_continuations(self, callback):
        response = requests.get(
            "https://raw.githubusercontent.com/erengy/anime-relations/master/anime-relations.txt",
            #            proxies={
            #                "https": config.proxy_auth_url,
            #                "http": config.proxy_auth_url,
            #            },
        )
        text_lines = response.text.split("\n")
        data_lines = [line for line in text_lines if line.startswith("- ")]
        entries = []
        checkset = set()
        for entry in data_lines:
            m = re.match(
                r"- (?P<mal_old>\d+|\?)\|(?P<kitsu_old>\d+|\?)\|(?P<alist_old>\d+|\?):(?P<old_ep>\d+)[-0-9]*"
                r" -> (?P<mal_new>\d+|\?)\|(?P<kitsu_new>\d+|\?)\|(?P<alist_new>\d+|\?):(?P<new_ep>\d+)[-0-9!]*",
                entry,
            )
            if m and m.group("mal_old") != "?":
                ep_shift = int(m.group("old_ep")) - int(m.group("new_ep"))
                entries.append((m.group("mal_old"), m.group("mal_new"), ep_shift))
                checkset.update({m.group("mal_old"), m.group("mal_new")})

        for anime_id in checkset:
            self.al.get_anime_by_aid(anime_id, cached=True)
        if entries:
            self.di.insert_new_sequel_data(entries)
