import os

import requests
from dotenv import load_dotenv

load_dotenv()

# token keys
token = os.getenv("BOT_TOKEN")
dev_tg_id = int(os.getenv("DEV_TG_ID"))
main_chat = int(os.getenv("MAIN_CHAT"))
gacha_chat = int(os.getenv("GACHA_CHAT"))
saucenao_token = os.getenv("SAUCENAO_TOKEN")

API_ERROR_LIMIT = 20
JIKAN_MAX_QUERY_LENGTH = 100
JIKAN_DELAY = 5

season_stats_file = os.getenv("SEASON_STATS_FILE")


class DB:
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    passwd = os.getenv("DB_PASSWD")
    db_name = os.getenv("DB_NAME")
    db_url = os.getenv("DB_URL").format(user, passwd, host, port, db_name)


# CUSTOM TIMEOUT jikan settings


HTTP_TIMEOUT = 10


class TimeoutRequestsSession(requests.Session):
    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", HTTP_TIMEOUT)
        return super(TimeoutRequestsSession, self).request(*args, **kwargs)


jikan_session = TimeoutRequestsSession()
jikan_params = dict(
    # selected_base='https://api.jikan.moe/v3',
    selected_base="https://katou.moe/jikan/v3",
    session=jikan_session,
)
