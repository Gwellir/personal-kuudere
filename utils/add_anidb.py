import json
import xml.etree.ElementTree as ET
import re
from Levenshtein import distance

from utils.db_wrapper2 import DataInterface
from orm.ORMWrapper import BaseRelations, Anime

with open('../data/anime-offline-database.json', 'r', encoding='utf-8') as f:
    lib = json.load(f)

conv = {
    12091: 33206, # https://myanimelist.net/anime/33206/Kobayashi-san_Chi_no_Maid_Dragon
    10729: 25099, # https://myanimelist.net/anime/25099/Ore_ga_Ojousama_Gakkou_ni_Shomin_Sample_Toshite_Gets♥Sareta_Ken
    10041: 20709, # Sabagebu
}

# some SYD OVA OAD
ignore = [10810, 8996, ]

for item in lib['data']:
    # print(item['title'])
    mal = anidb = al = None
    for link in item['sources']:
        if link.startswith('https://anidb.net'):
            anidb = re.match(r'.*/(\d+)', link).group(1)
            # print(anidb)
        elif link.startswith('https://myanimelist.net'):
            mal = re.match(r'.*/(\d+)', link).group(1)
            # print(mal)
        elif link.startswith('https://anilist.co'):
            al = re.match(r'.*/(\d+)', link).group(1)
            # print(mal)
    if not anidb:
        # print('ERROR')
        pass
    elif mal:
        conv[int(anidb)] = int(mal)
    elif al and int(al) < 50000 and int(anidb) not in conv:
        conv[int(anidb)] = int(al)

print('\n', len(conv))

tree = ET.parse('../data/ylguam.xml')
root = tree.getroot()
amount = 0
missing = []
for child in root:
    # print(child.tag, child.attrib)
    if int(child.attrib['id']) in conv:
        amount += 1
    else:
        missing.append((child.find('Name').text, int(child.attrib['id'])))


print(len(root), amount)
# print(missing)

di = DataInterface()
br = BaseRelations()
session = br.session

rels_list = session.query(Anime)\
    .with_entities(Anime.mal_aid, Anime.title, Anime.show_type, Anime.eps, Anime.status).all()
mal_dict = {item[0]: (item[1], item[2], item[3], item[4]) for item in rels_list}
missed_titles = [(item[0], item[1]) for item in rels_list if item[0] not in conv.values()]

for title in missing:
    dist = 1000
    match = None
    for comp in missed_titles:
        new_dist = distance(title[0].lower(), comp[1].lower())
        if new_dist < dist:
            dist = new_dist
            match = title, (comp[1], comp[0])
    print(dist, match)
    if dist < 9:
        conv[title[1]] = match[1][1]

for ign in ignore:
    if ign in conv:
        conv.pop(ign)


p_key = prev = None
for key in conv:
    if conv[key] == prev:
        print(p_key, prev, '->', key, conv[key])
    p_key, prev = key, conv[key]


animelist = []
status_conv = {
    'Finished Airing': 2,
    'Currently Airing': 1,
    'Not yet aired': 3,
}

for child in root:
    try:
        id_ = conv[int(child.attrib['id'])]
    except KeyError as e:
        print(e.args)
        continue

    vote_is_perm = False
    vote = child.find('UserPermVote')
    if not isinstance(vote, ET.Element):
        temp_vote = child.find('UserTempVote')
        vote = temp_vote
    else:
        vote_is_perm = True

    score = int(vote.text) if isinstance(vote, ET.Element) else 0
    total_eps = mal_dict[id_][2]
    if child.attrib['watched'] == "1":
        watched = 2
    elif score > 0:
        watched = 4
    else:
        watched = 6
    watched_eps = total_eps if child.attrib['watched'] == "1" else 0
    anime = {
        'mal_id': id_,
        'title': mal_dict[id_][0],
        'type': mal_dict[id_][1],
        'total_episodes': total_eps,
        'airing_status': status_conv[mal_dict[id_][3]],
        'watching_status': watched,
        'watched_episodes': watched_eps,
        'score': score,
    }
    animelist.append(anime)

di.delete_list_by_user_id(100000000)
di.insert_new_animelist(100000000, animelist)