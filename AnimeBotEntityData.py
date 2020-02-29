import re
import html
from collections import namedtuple

removal_patterns = re.compile(r'<.*>', re.I)
bb_re = re.compile(r'\[(/*[ib])\]')


manga_template = '''
<b>Title</b>: %s
<b>Title EN</b>: %s
<b>Type</b>: %s
<b>Status</b>: %s
<b>Chapters</b>: %s
<b>Volumes</b>: %s
<b>Released</b>: %s to %s
<b>Score</b>: %s
<a href="%s">***</a>
%s &lt;...&gt;
<b>MAL Page</b>: %s
'''


class AnimeEntry(namedtuple('AnimeEntry',
                            ['aired', 'airing', 'background', 'broadcast', 'duration', 'ending_themes', 'episodes',
                             'favorites', 'genres', 'headers', 'image_url', 'jikan_url', 'licensors', 'mal_id',
                             'members', 'opening_themes', 'popularity', 'premiered', 'producers', 'rank', 'rating',
                             'related', 'request_cache_expiry', 'request_cached', 'request_hash', 'score', 'scored_by',
                             'source', 'status', 'studios', 'synopsis', 'title', 'title_english', 'title_japanese',
                             'title_synonyms', 'trailer_url', 'type', 'url'])):
    anime_template = '''
    <b>Title</b>: %s
<b>Type</b>: %s
<b>Status</b>: %s
<b>Episodes</b>: %s
<b>Aired</b>: %s to %s
<b>Score</b>: %s
<a href="%s">***</a>
%s

<b><a href="%s">MAL Page</a></b>
    '''

    # def __init__(self):
    #     super().__init__()
    #     self.aired_from = self.aired['from']
    #     self.aired_to = self.aired['to']

    def __str__(self):
        return self.anime_template % (self.title, self.type, self.status, self.episodes if self.episodes else 'n/a',
                                      self.aired['from'][:10],
                                      self.aired['to'][:10] if self.aired['to'] else '...', self.score, self.image_url,
                                      self.synopsis[:500] + (' &lt;...&gt;' if len(self.synopsis) > 500 else ''),
                                      self.url,)

def synopsys_prep(synopsis):
    # text = html.unescape(bb_re.sub(r'<\1>', removal_patterns.sub('', synopsis, re.M), re.M))
    text = synopsis[:400].rsplit(' ', 1)[0]
    return text

class Gen_card(object):
    idnum = ""
    title = ""
    en_title = ""
    status = ""
    date_start = ""
    date_end = ""
    score = ""
    synopsis = ""
    image_url = ""
    link = ""


class Anime_card(Gen_card):
    anime_type = ""
    ep_num = ""

    def __init__(self, a_dict):
        self.mal_id = a_dict['mal_id']
        self.title = a_dict['title']
        self.title_english = a_dict['title_english']
        self.type = a_dict['type']
        self.status = a_dict['status']
        self.episodes = a_dict['episodes']
        # self.aired_from =
        # self.date_end = dates[1]
        # self.score = score
        # self.synopsis = synopsys_prep(synopsis)
        # # print(self.synopsis)
        # self.image_url = image_url
        # self.link = "http://myanimelist.net/anime/%s/" % aid

    def from_jikan(self, a_dict):
        mal_id = a_dict['mal_id']
        title = a_dict['title']
        title_english = a_dict['title_english']
        show_type = a_dict['type']
        status = a_dict['status']
        episodes = a_dict['episodes']
        aired_from = a_dict['aired']['from'][:19].replace('T', ' ')
        aired_to = a_dict['aired']['to'][:19].replace('T', ' ')
        score = a_dict['score']
        synopsis = a_dict['synopsis']
        # # print(self.synopsis)
        image_url = a_dict['image_url']
        link = f'http://myanimelist.net/anime/{mal_id}/'
        return self

    def output(self):
        return (self.title, self.anime_type, self.status, self.ep_num, self.date_start,
                self.date_end, self.score, self.image_url, self.synopsis, self.link)

    # def __repr__(self):
    #     return anime_template % self.output()


class Manga_card(Gen_card):
    manga_type = ""
    chapters = ""
    volumes = ""

    def __init__(self, mid, title, en_title, manga_type, status, chapters, volumes, dates,
                 score, synopsis, image_url):
        self.idnum = mid
        self.title = title
        self.en_title = en_title
        self.manga_type = manga_type
        self.status = status
        self.chapters = chapters
        self.volumes = volumes
        self.date_start = dates[0]
        self.date_end = dates[1]
        self.score = score
        self.synopsis = synopsys_prep(synopsis)
        # print(self.synopsis)
        self.image_url = image_url
        self.link = "http://myanimelist.net/manga/%s/" % mid

    def output(self):
        return (self.title, self.en_title, self.manga_type, self.status, self.chapters,
                self.volumes, self.date_start, self.date_end, self.score, self.image_url,
                self.synopsis, self.link)

    def __repr__(self):
        return manga_template % self.output()