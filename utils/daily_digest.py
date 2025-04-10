from datetime import datetime
from time import sleep

import requests


def get_air_datetime(entry):
    if not (aired := entry.get('aired')) or not (broadcast := entry.get('broadcast')):
        return None

    # fix the date to be in Japan TZ
    date_data = datetime.fromisoformat(aired['from'].replace("+00:00", "+09:00"))
    if not broadcast.get("time") or not broadcast.get("timezone"):
        return None

    time_data = broadcast.get("time").split(":")
    zone_data = broadcast.get("timezone")

    date_data = date_data.replace(hour=int(time_data[0]), minute=int(time_data[1]))
    return date_data.timestamp()


def get_season_from_jikan():
    """Returns list of dicts with fields name and MALID from Jikan source"""
    page = 1
    season_data = []
    while True:
        jikan_season_page = requests.get(f"https://api.jikan.moe/v4/seasons/now?sfw&page={page}").json()
        if page_data := jikan_season_page.get('data'):
            season_data.extend(page_data)
        if page == jikan_season_page.get('pagination').get('last_visible_page'):
            break
        page += 1
        sleep(4)

    unique_anime = set()
    filtered_data = []
    for a in season_data:
        if a['mal_id'] in unique_anime:
            continue
        else:
            unique_anime.add(a['mal_id'])
            filtered_data.append(a)

    return [
        {"name": entry["title"],
        "MALID": entry["mal_id"],
        "airdate_u": get_air_datetime(entry)}
        for entry in filtered_data if get_air_datetime(entry)
    ]



def get_digest():
    """Returns list of dicts with fields name and MALID"""
    now_date = datetime.now()
    season_num = (now_date.date().month - 1) // 3
    seasons = ["winter", "spring", "summer", "fall"]
    season_name = seasons[season_num]
    year = str(now_date.date().year)
    season = season_name + year
    season_data = requests.get(
        "https://www.senpai.moe/export.php?type=json&src=" + season
    ).json()

    if season_data.get("meta").get("season") != f"{season_name.capitalize()} {year}":
        season_items = get_season_from_jikan()
    else:
        season_items = season_data["items"]

    result = []
    for item in season_items:
        airdate_u = item["airdate_u"]
        if "simulcast_airdate_u" in item:
            airdate_u = item["simulcast_airdate_u"]
        name = item["name"]
        malid = item["MALID"]
        airdate = datetime.fromtimestamp(airdate_u)
        if airdate.date() > now_date.date():
            continue
        if now_date.weekday() != airdate.weekday():
            continue
        anime_obj = {"name": name, "mal_aid": malid, "time": airdate.time()}
        result.append(anime_obj.copy())
    return result
