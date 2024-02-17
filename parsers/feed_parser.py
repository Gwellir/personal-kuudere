# todo news and mangadex feeds

import re
import sys
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Optional

import requests
import rss_parser
from Levenshtein import distance
from pytz import timezone
from rss_parser.models.rss import RSS

import config
from logger.logger import FEEDPARSER_LOG

RESOLUTIONS = {
    "360p": 480,
    "480p": 480,
    "720x480": 480,
    "540p": 480,
    "720p": 720,
    "1280x720": 720,
    "1080p": 1080,
    "1920x1080": 1080,
}
match_in_square_brackets = re.compile(r"\[(.*?)\]")
match_in_round_brackets = re.compile(r"\((.*?)\)")
match_multiple_spaces = re.compile(r"\s+")
match_extension = re.compile(r".*\.(\w+)$")
match_ep_number = re.compile(r".*((?P<season>S\d+)E|- |episode )(\d+).*")
match_punct = re.compile(r"[/)(,:.!?+*☆♥★-]")


# todo well, this is a piece of shit
def get_closest_match_aid(variants, title) -> Optional[int]:
    min_dist = 6
    closest_match = None
    for v in variants:
        v_title = match_multiple_spaces.sub(
            " ", match_punct.sub(" ", v["title"].lower())
        ).strip()
        mal_id = v["mal_id"]
        if title.lower().startswith(f"{v_title} "):
            return mal_id
        d = distance(v_title, title)
        if d < min_dist:
            min_dist = d
            closest_match = mal_id
    return closest_match


def parse_size(description):
    """
    Gets the "size" part (in MiB) from torrent's feed entry description (returns 0 if below 1 MiB).
    Description example:
    <a href="https://nyaa.si/view/1224828">#1224828 |
    ( Dragontime ) My Hero Academia S04E18 1080P WEBRIP AAC2.0.H.264 DUAL AUDIO</a> |
     1.4 GiB |
      Anime - English-translated |
       48C16DA297AB1A2C9E65CADE9F532B0EFDEE658D

    :param description: Release description string

    :rtype: int
    """
    size_info = description.rsplit("|", 3)[1].strip().split(" ")
    size = int(float(size_info[0]))
    if size_info[1] == "KiB":
        size = 0
    elif size_info[1] == "GiB":
        size *= 1024
    return size


def get_resolution_from_tags(tags):
    """
    Checks list for tags related to typical video resolutions and returns a corresponding number

    :param tags: list of parsed tags

    :rtype: int
    """
    for tag in tags:
        if resolution := RESOLUTIONS.get(tag):
            return resolution
    return None


def extract_bracketed_tags(matcher, a_title: str, delims):
    tag_list = []
    start, end = delims
    matched_tags = matcher.findall(a_title)
    if matched_tags:
        for match in matched_tags:
            tag_list.extend(match.split(" "))
            a_title = a_title.replace(f"{start}{match}{end}", "").strip()

    return tag_list, a_title


def parse_feed_title(a_title: str):
    """
    Parses release title string.
    Looks for any parts of the title wrapped in square or round brackets and creates a tag list from them,
    tries to identify file extension, episode number and release resolution.
    Strips everything found and returns the remaining string as a title along with other relevant info.

    :param a_title: release title string

    :returns: tuple of (int, str, str, int, str)
    """
    a_ext = a_ep_no = a_group = None
    group_not_found = True
    all_tags = []
    tags_in_square, a_title = extract_bracketed_tags(
        match_in_square_brackets, a_title, ("[", "]")
    )
    if tags_in_square:
        a_group = tags_in_square[0]
        group_not_found = False
    tags_in_round, a_title = extract_bracketed_tags(
        match_in_round_brackets, a_title, ("(", ")")
    )
    if tags_in_round:
        if group_not_found:
            a_group = tags_in_round[0]
    all_tags.extend(tags_in_square + tags_in_round)

    FEEDPARSER_LOG.info(f"Tags: {all_tags}")
    a_res = get_resolution_from_tags(all_tags)
    extension = match_extension.match(a_title)
    if extension:
        a_ext = extension.group(1)
        a_title = str.replace(a_title, f".{a_ext}", "").strip()
    ep_number = match_ep_number.match(a_title)
    if ep_number:
        a_ep_no = ep_number.group(3)
        a_title = a_title[: a_title.find(f"{ep_number.group(1)}{ep_number.group(3)}")]
        if ep_number.group("season"):
            a_title += ep_number.group("season")
    a_title = match_punct.sub(" ", a_title)
    a_title = match_multiple_spaces.sub(" ", a_title).strip()
    if len(a_title) <= 2:
        a_title = f" {a_title}"
    return (
        int(a_ep_no) if a_ep_no else None,
        a_group[:90] if a_group else None,  # fix for group names which are too long
        a_title,
        a_res,
        a_ext,
    )


def get_local_time(dtime):
    dt_utc = datetime.strptime(dtime, "%a, %d %b %Y %H:%M:%S %z")
    return dt_utc.astimezone(timezone("Europe/Moscow"))


class TorrentFeedParser:
    """
    Handles retrieving and parsing nyaa.si rss feed, recognizing titles while matching them to MAL entries
    and downloading torrent files for further delivery.

    <Should be split up and named NyaaFeedParser after logic is changed to support multiple feed sources>
    """

    MY_FEEDS = [
        "https://nyaa.si/?page=rss&c=1_2&f=2",
        "https://nyaa.si/?page=rss&u=AkihitoSubsWeeklies",
        "https://nyaa.si/?page=rss&u=Ember_Encodes",
        "https://nyaa.si/?page=rss&u=sff",
    ]
    nyaa_time_fmt = "%a, %d %b %Y %H:%M:%S %z"

    def __init__(self, data_interface, anime_lookup):
        """
        Initializes requirements for feed parser

        :param data_interface: DataInterface DB connector instance
        :type data_interface: :class:`utils.db_wrapper2.DataInterface`
        :param anime_lookup: AnimeLookup instance
        :type anime_lookup: :class:`utils.anime_lookup.AnimeLookup`
        """
        self.di = data_interface
        self.al = anime_lookup

    def add_to_db(self, a_title, a_date, a_link, a_description, session):
        """
        Inserts an entry into database, or updates it in case of remote edits (very rare occurrence).

        :param a_title:
        :param a_date:
        :param a_link:
        :param a_description:
        :return:
        """
        if not self.di.select_feed_entry_by_title_and_date(
            a_title, a_date, session
        ).first():
            self.di.insert_new_feed_entry(
                a_title, a_date, a_link, a_description, session
            )
        else:
            self.di.update_anifeeds_entry(
                a_link, a_description, a_title, a_date, session
            )

    def get_last_entry(self):
        last_entry = self.di.select_last_feed_entry().first()
        return last_entry

    # todo scraping if no overlap?
    # todo SET MYSQL TIMEZONES
    def read_article_feed(self, rss_feed, session):
        """
        Parses new feed entries, checks for overlap with stored entries, prepares and stores data in database.

        :param rss_feed: Nyaa.si English-translated releases feed URL

        :return:
        """
        rss_ans = requests.get(rss_feed, proxies={"https": config.proxy_auth_url})
        if not rss_ans.status_code == HTTPStatus.OK:
            FEEDPARSER_LOG.error(
                f"Failed to get feed '{rss_feed}': {rss_ans.status_code}"
            )
            return

        parsed_feed: RSS = rss_parser.Parser.parse(rss_ans.text)

        last_db_entry = self.get_last_entry()
        d_3h = timedelta(hours=3)  # timezone hacks
        last_time = (last_db_entry[0] - d_3h).astimezone(timezone("Europe/Moscow"))
        last_title = last_db_entry[1]

        if not last_db_entry:
            entries = parsed_feed.channel.items
        else:
            entries = [
                entry
                for entry in parsed_feed.channel.items
                if get_local_time(entry.pub_date.content) > last_time
                or (
                    get_local_time(entry.pub_date.content) == last_time
                    and entry.title.content != last_title
                )
            ]
        entries.reverse()
        FEEDPARSER_LOG.info(
            f"Pulled {len(entries)}/{len(parsed_feed.channel.items)} new entries from '{rss_feed}'"
        )
        for article in entries:
            # todo suboptimal - calculating these twice
            dt = article.pub_date.content
            dt_local = get_local_time(dt)
            dt_repr = str(dt_local)[:19]
            self.add_to_db(
                article.title.content,
                dt_repr,
                article.link.content,
                article.description.content,
                session,
            )
            FEEDPARSER_LOG.info(
                f"Entry - {article.title.content} >> {article.link.content} >> {article.description.content} >> {article.pub_date.content}"
            )

    def check_feeds(self):
        """
        Main class function, checks feed(s) for new entries, stores them in DB and hands to the parser/torrent storage
        function.
        Should be called from outside this class.
        :return:
        """
        session = self.di.br.get_session()
        for feed in self.MY_FEEDS:
            self.read_article_feed(feed, session)
        release_list = self.di.select_unchecked_feed_entries(session).all()
        FEEDPARSER_LOG.info(
            f"Found {len(release_list)} unchecked entries in feeds table"
        )
        for release in release_list:
            result = self.do_recognize(
                release.title,
                release.date,
                release.link,
                parse_size(release.description),
                session,
            )  # just use a fucking hash as torrent identity
            if result and "unittest" not in sys.modules.keys():
                self.torrent_save(
                    *result,
                    session,
                )
        session.commit()
        session.close()

    def get_mal_ongoing_by_title(self, a_title, a_ep_no):
        import textwrap

        lines = textwrap.wrap(
            a_title, config.JIKAN_MAX_QUERY_LENGTH, break_long_words=False
        )
        query = lines[0]
        mal_id = None
        search_results = self.al.mal_search_by_name(query, ongoing=True)
        FEEDPARSER_LOG.debug(f"Found on MAL: {search_results}")
        # test for legit episode numbers as MAL sometimes returns very strange title matches
        mal_ids = [
            result["mal_id"]
            for result in search_results
            # if (
            #         result["episodes"] is not None
            #         and (result["episodes"] == 0 or result["episodes"] >= a_ep_no)
            # )
        ]

        FEEDPARSER_LOG.warning(f"Failed to resolve '{a_title}' precisely: {mal_ids}")
        if search_results and len(search_results) > 1:
            mal_id = get_closest_match_aid(search_results, query.lower())
        elif search_results:
            mal_id = mal_ids[0]
        return mal_id

    # todo batch parsing and delivery (possibly subscribe for complete seasons?)
    # todo fix parentheses adding spare spaces to recognized title name
    # todo avoid accidentally hitting SQL VARCHAR column size limits
    # todo version/recap parsing
    def do_recognize(self, a_title, a_date, torrent_link, file_size, session):
        """
        Tries to recognize a parsed title of an anime release, match it to its MAL entry, store relevant information
        in DB and save related torrent file for potential further delivery.

        :param a_title:
        :param torrent_link:
        :param file_size:
        :return:
        """
        save_title = a_title
        # todo parse title, should be replaced with anitopy I guess
        a_ep_no, a_group, a_title, a_res, a_ext = parse_feed_title(a_title)

        # possible recognizable ongoing
        if a_ep_no and a_group and a_title:
            FEEDPARSER_LOG.info(
                f'"{a_title}" #{a_ep_no} by [{a_group}], res ({a_res if a_res else "n/a"})'
                f' ext ({a_ext if a_ext else "n/a"})'
            )
            # exact synonym match to title only
            mal_id, ep_shift = self.di.select_ongoing_anime_id_by_synonym(
                a_title, session
            )
            if ep_shift <= a_ep_no:
                a_ep_no = a_ep_no - ep_shift
                FEEDPARSER_LOG.info(f"Synonym match: {mal_id}")
                if not mal_id:
                    mal_ids = self.di.select_mal_anime_ids_by_title_part(
                        a_title, session
                    )
                    FEEDPARSER_LOG.info(
                        f"Searching for '*{a_title}*' in ongoings... Found {mal_ids}"
                    )
                    if mal_ids and len(mal_ids) == 1:
                        FEEDPARSER_LOG.info(f"Title part match: {mal_ids[0]}")
                        mal_id = mal_ids[0]
                    # elif not mal_ids:
                    # todo unify lurking and title comparison
                    else:
                        mal_id = self.get_mal_ongoing_by_title(a_title, a_ep_no)
                    # check whether we have title info
                    if mal_id:
                        self.al.get_anime_by_aid(mal_id)
                        # todo sometimes a double can make it here despite synonym check
                        self.di.insert_new_synonym(mal_id, a_title)
            self.di.update_anifeeds_with_parsed_information(
                mal_id,
                a_group,
                a_res,
                a_ep_no,
                file_size,
                save_title,
                a_date,
                session,
            )
            if mal_id:
                return mal_id, a_group, a_ep_no, torrent_link, a_title, a_res, file_size

        else:
            FEEDPARSER_LOG.info(f'Not recognized "{save_title}"')
            self.di.update_anifeeds_unrecognized_entry(
                file_size, save_title, a_date, session
            )
        return

    # todo implement actual check for files which failed to download
    def torrent_save(self, mal_id, group, episode, link, title, res, size, session):
        """
        Downloads, names and saves a torrent file using information from a parsed nyaa.si feed entry.

        :param mal_id:
        :param group:
        :param episode:
        :param link:
        :param title:
        :param res:
        :param size:
        :returns: Name of local torrent file
        """
        approved_ep = self.di.select_last_ongoing_ep_by_id(mal_id, session).one()
        if approved_ep and int(episode) > approved_ep[0]:
            FEEDPARSER_LOG.info(f"  >>> FAKE {title} - {episode} by {group}")
            return
        is_downloaded = False
        title = re.sub(r"[|/\\?:<>]", " ", title)
        r = requests.get(link, proxies={"https": config.proxy_auth_url})
        filename = (
            f"torrents/[{group}] {title}({mal_id}) - {episode:0>2}"
            + (f" [{res}p]" if res else "")
            + f" [{size} MiB].torrent"
        )
        f = open(filename, "wb")
        if f:
            f.write(r.content)
            is_downloaded = True
            f.close()
            FEEDPARSER_LOG.info(
                f'Downloaded "{link}" for {title}({mal_id}) ep {episode} from {group}, size - {size}'
            )
        if is_downloaded:
            entry_exists = self.di.select_torrent_is_saved_in_database(
                mal_id, group, episode, res, size, session
            ).first()
            if not entry_exists:
                self.di.insert_new_torrent_file(
                    mal_id, group, episode, filename, res, size, session
                )
            else:
                FEEDPARSER_LOG.info(
                    f"DUPLICATE: {mal_id} by {group} ep.{episode} res {res} size {size}"
                )
            return filename
        else:
            return False
