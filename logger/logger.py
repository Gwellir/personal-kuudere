import logging

# set up logging to file - see previous section for more details
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    datefmt="%m-%d %H:%M",
    filename="log/tgbot.log",
    filemode="a",
)
# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
# set a format which is simpler for console use
formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger("").addHandler(console)

TELEGRAM_LOG = logging.getLogger("tgbot")
LISTPARSER_LOG = logging.getLogger("lists")
FEEDPARSER_LOG = logging.getLogger("feeds")
DATABASE_LOG = logging.getLogger("database")
ANIMEBASE_LOG = logging.getLogger("animebase")

logging.getLogger("telegram.bot").setLevel(logging.INFO)
logging.getLogger("telegram.ext.dispatcher").setLevel(logging.INFO)
