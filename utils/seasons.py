from datetime import datetime, timedelta

from orm.ORMWrapper import Anime

MONTH_TO_SEASON = {
    0: "fall",
    1: "winter",
    2: "winter",
    3: "winter",
    4: "spring",
    5: "spring",
    6: "spring",
    7: "summer",
    8: "summer",
    9: "summer",
    10: "fall",
    11: "fall",
    12: "fall",
    13: "winter",
}


def get_season_from_date(date: datetime, is_end_date: bool = False) -> str:
    year = date.year
    month = date.month
    if not is_end_date:
        if month % 3 == 0 and date.day > 15:
            month += 1
        if month > 12:
            year += 1
    else:
        if month % 3 == 1 and date.day < 15:
            month -= 1
        if month < 1:
            year -= 1
    season = MONTH_TO_SEASON[month]

    return f"{season} {year}"


def get_season_interval(season_str: str) -> list:
    NEXT_SEASON = {
        "fall": "winter",
        "winter": "spring",
        "spring": "summer",
        "summer": "fall",
    }

    while True:
        season, year_str = season_str.split()
        year = int(year_str)
        season = NEXT_SEASON[season]
        if season == "winter":
            year += 1
        season_str = f"{season} {year}"
        yield season_str


def get_actual_seasons(anime: Anime) -> list:
    if anime.premiered:
        start_season = anime.premiered.lower()
    elif anime.started_at:
        start_season = get_season_from_date(anime.started_at)
    else:
        return []
    if anime.show_type == "TV" and anime.status == "Finished Airing":
        if anime.ended_at:
            end_date = anime.ended_at
        elif anime.eps and anime.eps > 0:
            end_date = anime.started_at + timedelta(weeks=anime.eps - 1)
        else:
            return []
    elif anime.status == "Currently Airing":
        if anime.eps and anime.eps > 0:
            end_date = anime.started_at + timedelta(weeks=anime.eps - 1)
        else:
            end_date = datetime.now()
    elif anime.status == "Not yet aired":
        return []
    elif anime.show_type in ["ONA", "OVA", "Movie"] and anime.status != "Not yet aired":
        end_date = anime.started_at + timedelta(days=91)
    else:
        return []

    end_season = get_season_from_date(end_date, is_end_date=True)
    interval = [start_season]
    for season_str in get_season_interval(start_season):
        interval.append(season_str)
        if season_str == end_season:
            break

    return interval
