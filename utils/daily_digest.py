import datetime

import requests


def get_digest():
    """Returns list of dicts with fields name and MALID"""
    now_date = datetime.datetime.now()
    season_num = (now_date.date().month - 1) // 3
    seasons = ["winter", "spring", "summer", "fall"]
    season = seasons[season_num] + str(now_date.date().year)
    raw = requests.get(
        "https://www.senpai.moe/export.php?type=json&src=" + season
    ).json()
    result = []
    for item in raw["items"]:
        airdate_u = item["airdate_u"]
        if "simulcast_airdate_u" in item:
            airdate_u = item["simulcast_airdate_u"]
        name = item["name"]
        malid = item["MALID"]
        airdate = datetime.datetime.fromtimestamp(airdate_u)
        if airdate.date() > now_date.date():
            continue
        if now_date.weekday() != airdate.weekday():
            continue
        anime_obj = {"name": name, "mal_aid": malid}
        result.append(anime_obj.copy())
    return result
