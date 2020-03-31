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


class AnimeEntry(namedtuple('AnimeEntry',
                            ['aired', 'airing', 'background', 'broadcast', 'duration', 'ending_themes', 'episodes',
                             'favorites', 'genres', 'headers', 'image_url', 'jikan_url', 'licensors', 'mal_id',
                             'members', 'opening_themes', 'popularity', 'premiered', 'producers', 'rank', 'rating',
                             'related', 'request_cache_expiry', 'request_cached', 'request_hash', 'score', 'scored_by',
                             'source', 'status', 'studios', 'synopsis', 'title', 'title_english', 'title_japanese',
                             'title_synonyms', 'trailer_url', 'type', 'url'])):

    def __str__(self):
        return anime_template % (self.title, self.type, self.status, self.episodes if self.episodes else 'n/a',
                                 self.aired['from'][:10] if self.aired['from'] else '...',
                                 self.aired['to'][:10] if self.aired['to'] else '...', self.score, self.image_url,
                                 (self.synopsis[:500] + (' &lt;...&gt;' if len(self.synopsis) > 500 else ''))
                                 if self.synopsis else '[No synopsis available.]', self.url,)
