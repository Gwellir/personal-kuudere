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

MAL_API_TOKEN = os.getenv("MAL_API_TOKEN")
MAL_API_LIST_PAGE_SIZE = int(os.getenv("MAL_API_LIST_PAGE_SIZE"))

season_stats_file = os.getenv("SEASON_STATS_FILE")

proxy_address = os.getenv("PROXY_ADDRESS")
proxy_username = os.getenv("PROXY_USERNAME")
proxy_password = os.getenv("PROXY_PASSWORD")
proxy_schema = os.getenv("PROXY_SCHEMA")
proxy_auth_url = f"{proxy_schema}://{proxy_username}:{proxy_password}@{proxy_address}"
proxy_url = f"{proxy_schema}://{proxy_address}"


vk_token = os.getenv("VK_TOKEN")


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
    selected_base="https://api.jikan.moe/v4",
    # selected_base="https://katou.moe/jikan/v3",
    session=jikan_session,
)
