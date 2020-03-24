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


def parse_size(desc):
    size_info = desc.rsplit("|", 3)[1].strip().split(" ")
    size = int(float(size_info[0]))
    if size_info[1] == "KiB":
        size = 0
    elif size_info[1] == "GiB":
        size *= 1024
    return size


def get_resolution_from_params(params):
    resolution = None
    if [x for x in CATCH_720 if x in [p.lower() for p in params]]:
        resolution = 720
    elif [x for x in CATCH_1080 if x in [p.lower() for p in params]]:
        resolution = 1080
    elif [x for x in CATCH_480 if x in [p.lower() for p in params]]\
            or [x for x in CATCH_360 if x in [p.lower() for p in params]]:
        resolution = 480
    return resolution


def parse_feed_title(a_title):
    re_fa = re.findall(r'\[(.*?)\]', a_title)
    a_ext = a_ep_no = a_group = None
    group_not_found = True
    params = []
    if re_fa:
        a_group = re_fa[0]
        group_not_found = False
        for match in re_fa:
            params.extend(match.split(' '))
            a_title = str.replace(a_title, f'[{match}]', '').strip()
    re_fa = re.findall(r'\((.*?)\)', a_title)
    if re_fa:
        if group_not_found:
            a_group = re_fa[0]
        for match in re_fa:
            params.extend(match.split(' '))
            a_title = str.replace(a_title, f'({match})', '').strip()
    print(f'{Fore.BLUE}{params}{Style.RESET_ALL}')
    a_res = get_resolution_from_params(params)
    re_ext = re.match(r'.*\.(\w+)$', a_title)
    if re_ext:
        a_ext = re_ext.group(1)
        a_title = str.replace(a_title, f'.{a_ext}', '').strip()
    re_ep_no = re.match(r'.*((?P<season>S\d+)E|- |episode )(\d+).*', a_title)
    if re_ep_no:
        a_ep_no = re_ep_no.group(3)
        a_title = a_title[:a_title.find(f'{re_ep_no.group(1)}{re_ep_no.group(3)}')]
        if re_ep_no.group('season'):
            a_title += re_ep_no.group('season')
        a_title = a_title.strip()
    return a_ep_no, a_group, a_title, a_res, a_ext


def get_local_time(dtime):
    dt_utc = datetime(*dtime[0:6])
    return dt_utc.astimezone(timezone('Europe/Moscow'))


class TorrentFeedParser:
    MY_FEEDS = ['https://nyaa.si/?page=rss&c=1_2&f=0']
    nyaa_time_fmt = "%a, %d %b %Y %H:%M:%S %z"

    def __init__(self, ani_db, jikan):
        self.jikan = jikan
        self.ani_db = ani_db

    # def article_not_in_db(self, a_title, a_date):
    #     article = self.ani_db.select('*', 'anifeeds', 'title = %s AND date = %s', [a_title, a_date], quiet=True)
    #     return not article

    def add_to_db(self, a_title, a_date, a_link, a_description):
        # do_recognize(a_title)
        if not self.ani_db.select('*', 'anifeeds', 'title = %s and date = %s', [a_title, a_date]):
            self.ani_db._cursor.execute("INSERT into anifeeds (title, date, link, description)"
                                        "VALUES (%s,%s,%s,%s)", (a_title, a_date, a_link, a_description))
        else:
            self.ani_db.update('anifeeds', 'link = %s, description = %s',
                               [a_link, a_description], 'title = %s and date = %s', [a_title, a_date])
        self.ani_db.commit()

    def get_last_entry(self):
        last_entry = self.ani_db.select('date, title', 'anifeeds', 'TRUE order by date desc limit %s', [1])
        self.ani_db.commit()
        return last_entry

    # todo scraping if no overlap?
    # todo SET TIMEZONES
    def read_article_feed(self, feed):
        feed = feedparser.parse(feed)
        last_entry = self.get_last_entry()
        d_3h = timedelta(hours=3)
        last_time = (last_entry[0][0] - d_3h).astimezone(timezone('Europe/Moscow'))
        last_title = last_entry[0][1]
        if not last_entry:
            entries = [entry for entry in feed['entries']]
        else:
            entries = [entry for entry in feed['entries']
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
        for f in self.MY_FEEDS:
            self.read_article_feed(f)
        a_list = self.ani_db.select('*', 'anifeeds', 'checked = %s order by date', [0])
        for anime in a_list:
            self.do_recognize(anime[0], anime[2], parse_size(anime[3]))  # just use a fucking hash as torrent identity
        self.ani_db.commit()
        # self.ani_db.close()

    # todo fix parentheses adding spare spaces to recognized title name
    # todo avoid accidentally hitting SQL VARCHAR column size limits
    # todo version/recap parsing
    def do_recognize(self, a_title, t_link, f_size):
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
                    sr = self.jikan.search('anime', a_title, page=2,
                                           parameters={'type': 'tv', 'status': 'airing', 'limit': 5, 'genre': 15,
                                                       'genre_exclude': 0})
                    sleep(2)
                    # test for legit episode numbers as MAL sometimes returns very strange title matches
                    mal_ids = [(result['mal_id'],) for result in sr['results']
                               if (result['episodes'] == 0 or result['episodes'] >= int(a_ep_no))]
                if len(mal_ids) == 1:
                    print(mal_ids[0][0])
                    mal_id = int(mal_ids[0][0])
                    # ani_db.update('anifeeds', 'mal_aid = %s, a_group = %s, resolution = %s, ep = %s ',
                    #               [mal_id, a_group, a_res, int(a_ep_no)], f'title = %s', [save_title])
                else:
                    print(f"Can't get a precise result... {mal_ids}")
                    mal_id = title_compare(sr['results'], a_title)
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
                               [mal_id, a_group, a_res, int(a_ep_no), f_size, 1], 'title = %s', [save_title])
            self.ani_db.commit()
            if mal_id:
                self.torrent_save(mal_id, a_group, a_ep_no, t_link, a_title, a_res, f_size)
        else:
            print(f'{Fore.RED}Not recognized "{save_title}"{Style.RESET_ALL}')
            self.ani_db.update('anifeeds', 'checked = %s, size = %s', [1, f_size], 'title = %s', [save_title])
            self.ani_db.commit()
        return

    # todo implement actual check for files which failed to download
    def torrent_save(self, mal_id, group, episode, link, title, res, size):
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
            test = self.ani_db.select('*', 'torrent_files',
                                      'mal_aid = %s and a_group = %s and episode = %s and res = %s and file_size = %s',
                                      [mal_id, group, episode, res, size])
            if not test:
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
