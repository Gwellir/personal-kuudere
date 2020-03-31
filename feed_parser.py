# todo news and mangadex feeds

import feedparser
import re
from colorama import Fore, Style
from pprint import pprint
from time import sleep
from collections import Counter
import requests
from pytz import timezone
from datetime import datetime, timedelta


CATCH_360 = ['360p']
CATCH_480 = ['480p', '720x480']
CATCH_720 = ['720p', '1280x720']
CATCH_1080 = ['1080p', '1920x1080']
match_in_square_brackets = re.compile(r'\[(.*?)\]')
match_in_round_brackets = re.compile(r'\((.*?)\)')
match_extension = re.compile(r'.*\.(\w+)$')
match_ep_number = re.compile(r'.*((?P<season>S\d+)E|- |episode )(\d+).*')


# todo well, this is a piece of shit
def title_compare(variants, title):
    t = Counter(title.lower())
    # min_sum = sum(t.values())
    for v in variants:
        c = Counter(v['title'].lower())
        diff = (t - c) if len(title) > len(v['title']) else (c - t)
        print(diff, sum(diff.values()), v['title'])
        if sum(diff.values()) < 5 and sum(diff.values()) < len(title) / 3:
            return v['mal_id']
    return None


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
    resolution = None
    if [res for res in CATCH_720 if res in [t.lower() for t in tags]]:
        resolution = 720
    elif [res for res in CATCH_1080 if res in [t.lower() for t in tags]]:
        resolution = 1080
    elif [res for res in CATCH_480 if res in [t.lower() for t in tags]]\
            or [res for res in CATCH_360 if res in [t.lower() for t in tags]]:
        resolution = 480
    return resolution


def parse_feed_title(a_title):
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
    tags_in_square = match_in_square_brackets.findall(a_title)
    if tags_in_square:
        a_group = tags_in_square[0]
        group_not_found = False
        for match in tags_in_square:
            all_tags.extend(match.split(' '))
            a_title = str.replace(a_title, f'[{match}]', '').strip()
    tags_in_round = match_in_round_brackets.findall(a_title)
    if tags_in_round:
        if group_not_found:
            a_group = tags_in_round[0]
        for match in tags_in_round:
            all_tags.extend(match.split(' '))
            a_title = str.replace(a_title, f'({match})', '').strip()
    print(f'{Fore.BLUE}{all_tags}{Style.RESET_ALL}')
    a_res = get_resolution_from_tags(all_tags)
    extension = match_extension.match(a_title)
    if extension:
        a_ext = extension.group(1)
        a_title = str.replace(a_title, f'.{a_ext}', '').strip()
    ep_number = match_ep_number.match(a_title)
    if ep_number:
        a_ep_no = ep_number.group(3)
        a_title = a_title[:a_title.find(f'{ep_number.group(1)}{ep_number.group(3)}')]
        if ep_number.group('season'):
            a_title += ep_number.group('season')
        a_title = a_title.strip()
    return a_ep_no, a_group, a_title, a_res, a_ext


def get_local_time(dtime):
    dt_utc = datetime(*dtime[0:6])
    return dt_utc.astimezone(timezone('Europe/Moscow'))


class TorrentFeedParser:
    """
    Handles retrieving and parsing nyaa.si rss feed, recognizing titles while matching them to MAL entries
    and downloading torrent files for further delivery.

    <Should be split up and named NyaaFeedParser after logic is changed to support multiple feed sources>
    """
    MY_FEEDS = ['https://nyaa.si/?page=rss&c=1_2&f=0']
    nyaa_time_fmt = "%a, %d %b %Y %H:%M:%S %z"

    def __init__(self, ani_db, jikan):
        self.jikan = jikan
        self.ani_db = ani_db

    def add_to_db(self, a_title, a_date, a_link, a_description):
        """
        Inserts an entry into database, or updates it in case of remote edits (very rare occurrence).
        :param a_title:
        :param a_date:
        :param a_link:
        :param a_description:
        :return:
        """
        if not self.ani_db.select('*', 'anifeeds', 'title = %s and date = %s', [a_title, a_date]):
            self.ani_db._cursor.execute("INSERT into anifeeds (title, date, link, description)"
                                        "VALUES (%s,%s,%s,%s)", (a_title, a_date, a_link, a_description))
        else:
            self.ani_db.update('anifeeds', 'link = %s, description = %s',
                               [a_link, a_description], 'title = %s and date = %s', [a_title, a_date])
        self.ani_db.commit()

    def get_last_entry(self):
        last_entry = self.ani_db.select('date, title', 'anifeeds', 'TRUE order by date desc limit %s', [1])
        self.ani_db.commit()  # todo spare commits probably not needed anymore
        return last_entry

    # todo scraping if no overlap?
    # todo SET MYSQL TIMEZONES
    def read_article_feed(self, rss_feed):
        """
        Parses new feed entries, checks for overlap with stored entries, prepares and stores data in database.
        :param rss_feed: Nyaa.si English-translated releases feed URL
        :return:
        """
        parsed_feed = feedparser.parse(rss_feed)
        last_db_entry = self.get_last_entry()
        d_3h = timedelta(hours=3)  # timezone hacks
        last_time = (last_db_entry[0][0] - d_3h).astimezone(timezone('Europe/Moscow'))
        last_title = last_db_entry[0][1]
        if not last_db_entry:
            entries = [entry for entry in parsed_feed['entries']]
        else:
            entries = [entry for entry in parsed_feed['entries']
                       if get_local_time(entry.published_parsed) > last_time
                       or (get_local_time(entry.published_parsed) == last_time
                           and entry['title'] != last_title)]
        entries.reverse()
        # pprint(entries)
        for article in entries:
            # todo suboptimal - calculating these twice
            dt = article.published_parsed
            dt_local = get_local_time(dt)
            dt_repr = str(dt_local + d_3h)[:19]
            self.add_to_db(article['title'], dt_repr, article['link'], article['description'])
            print(f'{article.title}\n{article.link}\n{article.description}\n{article.published}')

    def check_feeds(self):
        """
        Main class function, checks feed(s) for new entries, stores them in DB and hands to the parser/torrent storage
        function.
        Should be called from outside this class.
        :return:
        """
        for feed in self.MY_FEEDS:
            self.read_article_feed(feed)
        release_list = self.ani_db.select('*', 'anifeeds', 'checked = %s order by date', [0])
        for release in release_list:
            self.do_recognize(release[0], release[2], parse_size(release[3]))  # just use a fucking hash as torrent identity
        self.ani_db.commit()
        # self.ani_db.close()

    # todo batch parsing and delivery (possibly subscribe for complete seasons?)
    # todo fix parentheses adding spare spaces to recognized title name
    # todo avoid accidentally hitting SQL VARCHAR column size limits
    # todo version/recap parsing
    def do_recognize(self, a_title, torrent_link, file_size):
        """
        Tries to recognize a parsed title of an anime release, match it to its MAL entry, store relevant information
        in DB and save related torrent file for potential further delivery.
        :param a_title:
        :param torrent_link:
        :param file_size:
        :return:
        """
        save_title = a_title
        a_ep_no, a_group, a_title, a_res, a_ext = parse_feed_title(a_title)
        if a_ep_no and a_group and a_title:
            print(f'"{a_title}" #{a_ep_no} by [{a_group}], res ({a_res if a_res else "n/a"})'
                  f' ext ({a_ext if a_ext else "n/a"})')
            mal_id = self.ani_db.select('mal_aid', 'anime_x_synonyms', 'synonym = %s', [a_title])
            if not mal_id:
                mal_ids = self.ani_db.select('DISTINCT mal_aid', 'list_status',
                                             '`title` like %s and `show_type` = "TV" and `airing` = 1', [a_title])
                if not mal_ids:
                    search_results = self.jikan.search('anime', a_title, page=2,
                                           parameters={'type': 'tv', 'status': 'airing', 'limit': 5, 'genre': 15,
                                                       'genre_exclude': 0})
                    sleep(2)
                    # test for legit episode numbers as MAL sometimes returns very strange title matches
                    mal_ids = [(result['mal_id'],) for result in search_results['results']
                               if (result['episodes'] == 0 or result['episodes'] >= int(a_ep_no))]
                if len(mal_ids) == 1:
                    print(mal_ids[0][0])
                    mal_id = int(mal_ids[0][0])
                    # ani_db.update('anifeeds', 'mal_aid = %s, a_group = %s, resolution = %s, ep = %s ',
                    #               [mal_id, a_group, a_res, int(a_ep_no)], f'title = %s', [save_title])
                else:
                    print(f"Can't get a precise result... {mal_ids}")
                    mal_id = title_compare(search_results['results'], a_title)
                # check whether we have title info
                if mal_id:
                    if not self.ani_db.select('mal_aid', 'anime', 'mal_aid = %s', [mal_id]):
                        a_info = self.jikan.anime(mal_id)
                        sleep(2)
                        # is sometimes unreachable
                        self.ani_db._cursor.execute('insert into anime values'
                                                    '(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                                    (a_info['mal_id'], a_info['title'], a_info['title_english'],
                                                     a_info['title_japanese'], a_info['synopsis'], a_info['type'],
                                                     a_info['aired']['from'][:19].replace('T', ' '),
                                                     a_info['aired']['to'][:19].replace('T', ' ') if
                                                     a_info['aired']['to'] else None,
                                                     None, None,  # broadcast
                                                     0 if not a_info['episodes'] else a_info['episodes'],
                                                     a_info['image_url'], a_info['score'], None,))  # status
                    self.ani_db._cursor.execute("insert anime_x_synonyms values (%s, %s)", (mal_id, a_title))
            else:
                mal_id = mal_id[0][0]
            self.ani_db.update('anifeeds',
                               'mal_aid = %s, a_group = %s, resolution = %s, ep = %s, size = %s, checked = %s',
                               [mal_id, a_group, a_res, int(a_ep_no), file_size, 1], 'title = %s', [save_title])
            self.ani_db.commit()
            if mal_id:
                self.torrent_save(mal_id, a_group, a_ep_no, torrent_link, a_title, a_res, file_size)
        else:
            print(f'{Fore.RED}Not recognized "{save_title}"{Style.RESET_ALL}')
            self.ani_db.update('anifeeds', 'checked = %s, size = %s', [1, file_size], 'title = %s', [save_title])
            self.ani_db.commit()
        return

    # todo implement actual check for files which failed to download
    def torrent_save(self, mal_id, group, episode, link, title, res, size):
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
        is_downloaded = False
        title = re.sub(r'[|/\\?:<>]', ' ', title)
        url = link
        r = requests.get(url)
        filename = f'torrents/[{group}] {title} - {episode:0>2}' + (f' [{res}p]' if res else '') + f' [{size} MiB].torrent'
        f = open(filename, 'wb')
        if f:
            f.write(r.content)
            is_downloaded = True
            f.close()
            print(f'Downloaded "{link}" for {title}({mal_id}) ep {episode} from {group}, size - {size}')
        if is_downloaded:
            entry_exists = self.ani_db.select('*', 'torrent_files',
                                      'mal_aid = %s and a_group = %s and episode = %s and res = %s and file_size = %s',
                                      [mal_id, group, episode, res, size])
            if not entry_exists:
                self.ani_db._cursor.execute("insert torrent_files values (%s, %s, %s, %s, %s, %s)",
                                            (mal_id, group, episode, filename, res, size))
                self.ani_db.commit()
            else:
                print('DUPLICATE ', [mal_id, group, episode, res, size])
            return filename
        else:
            return False

#
# if __name__ == '__main__':
#     parser = TorrentFeedParser()
#     parser.check_feeds()
