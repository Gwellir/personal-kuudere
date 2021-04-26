# from pprint import pprint
from time import sleep
from typing import List, Optional

import jikanpy
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.mysql import (
    BIGINT,
    ENUM,
    INTEGER,
    JSON,
    SMALLINT,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql.functions import now

# from datetime import datetime
import config

Base = declarative_base()
metadata = Base.metadata


class BaseRelations:
    def __init__(self):
        self._engine = create_engine(
            config.DB.db_url, echo=True, pool_pre_ping=True, pool_recycle=3600
        )

        self._SessionFactory = sessionmaker(bind=self._engine)
        self.connection = None

    def get_session(self):
        session = self._SessionFactory()
        return session


br = BaseRelations()
jikan = jikanpy.Jikan()


class Anime(Base):
    __tablename__ = "anime"

    mal_aid = Column(BIGINT(20), primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    title_english = Column(String(255))
    title_japanese = Column(String(255))
    synopsis = Column(Text)
    show_type = Column(
        ENUM("TV", "Movie", "OVA", "Special", "ONA", "Music", "Other", "Unknown")
    )
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    episodes = Column(SMALLINT(5))
    image_url = Column(String(100))
    score = Column(Float)
    status = Column(String(30))
    background = Column(Text)
    broadcast = Column(String(40))
    duration = Column(String(30))
    favorites = Column(INTEGER(10))
    members = Column(INTEGER(10))
    popularity = Column(INTEGER(10))
    premiered = Column(String(20))
    rank = Column(INTEGER(10))
    rating = Column(String(50))
    scored_by = Column(INTEGER(10))
    source = Column(String(20))
    trailer_url = Column(String(100))
    ending_themes = Column(JSON)
    related = Column(JSON)
    opening_themes = Column(JSON)
    title_synonyms = Column(JSON)

    genres = relationship("Genres", secondary="anime_x_genres")
    licensors = relationship("Licensors", secondary="anime_x_licensors")
    producers = relationship("Producers", secondary="anime_x_producers")
    studios = relationship("Studios", secondary="anime_x_studios")

    synced = Column(DateTime, default=now)

    def __repr__(self):
        return f"<b>Title</b>: %s\n<b>Type</b>: %s\n<b>Status</b>: %s\n<b>Episodes</b>: %s\n<b>Aired</b>: %s to %s\n" f"<b>Score</b>: %s\n<a href='%s'>***</a>\n%s\n\n<b><a href='https://myanimelist.net/anime/%s'>MAL Page</a></b>" % (
            self.title,
            self.show_type,
            self.status,
            self.episodes if self.episodes else "n/a",
            self.started_at.date() if self.started_at else "...",
            self.ended_at.date() if self.ended_at else "...",
            self.score,
            self.image_url,
            (self.synopsis[:500] + (" &lt;...&gt;" if len(self.synopsis) > 500 else ""))
            if self.synopsis
            else "[No synopsis available.]",
            self.mal_aid,
        )


class Characters(Base):
    __tablename__ = "characters"

    mal_cid = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    name_kanji = Column(String, nullable=True)
    about = Column(Text)
    image_url = Column(String, nullable=True)

    anime: List[Anime] = relationship(
        "Anime", secondary="anime_x_characters", backref="characters"
    )

    @classmethod
    def get_or_create(cls, cid, session) -> Optional["Characters"]:
        char = session.query(Characters).filter_by(mal_cid=cid).first()
        if not char:
            try:
                remote_char = jikan.character(cid)
            except jikanpy.exceptions.APIException as e:
                print("Chars get_or_create", e.args)
                return None
            sleep(config.jikan_delay)
            anime_ids = [entry["mal_id"] for entry in remote_char["animeography"]]
            related_anime = (
                session.query(Anime).filter(Anime.mal_aid.in_(anime_ids)).all()
            )
            char = Characters(
                mal_cid=cid,
                name=remote_char["name"],
                name_kanji=remote_char["name_kanji"],
                about=remote_char["about"],
                image_url=remote_char["image_url"],
                anime=related_anime,
            )
            session.add(char)
            session.commit()

        return char


class SeasonalVotings(Base):
    __tablename__ = "seasonal_votings"

    id = Column(Integer, primary_key=True)
    season = Column(String, nullable=False, unique=True)
    is_current = Column(Boolean, nullable=False, default=False)

    characters = relationship(
        "Characters", secondary="voted_characters", backref="votings"
    )


class VotedCharacters(Base):
    __tablename__ = "voted_characters"
    __table_args__ = (UniqueConstraint("name", "title", name="voted_characters_un"),)

    id = Column(Integer, primary_key=True)
    vid = Column(Integer, ForeignKey("seasonal_votings.id"), nullable=False, index=True)
    mal_cid = Column(Integer, ForeignKey("characters.mal_cid"), nullable=True)
    name = Column(String, nullable=True)
    title = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    is_posted = Column(Boolean, nullable=False, default=False)
    mal_aid = Column(Integer, ForeignKey("anime.mal_aid"), nullable=False)

    voting = relationship("SeasonalVotings")
    character = relationship("Characters")
    anime = relationship("Anime")


class Ongoings(Base):
    __tablename__ = "ongoings"

    mal_aid = Column(ForeignKey("anime.mal_aid"), primary_key=True, index=True)
    last_ep = Column(SMALLINT(6), nullable=False)
    last_release = Column(DateTime, nullable=False, index=True)


class Genres(Base):
    __tablename__ = "genres"

    mal_gid = Column(BIGINT(20), primary_key=True)
    name = Column(String(30))


class Licensors(Base):
    __tablename__ = "licensors"

    name = Column(String(255), primary_key=True)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


class Producers(Base):
    __tablename__ = "producers"

    mal_pid = Column(BIGINT(20), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


class Studios(Base):
    __tablename__ = "studios"

    mal_sid = Column(BIGINT(20), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


class AniFeeds(Base):
    __tablename__ = "anifeeds"

    title = Column(VARCHAR(255), primary_key=True, nullable=False, index=True)
    date = Column(
        DateTime,
        primary_key=True,
        nullable=False,
        index=True,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    link = Column(String(50, "utf8mb4_general_ci"))
    description = Column(Text(collation="utf8mb4_general_ci"))
    mal_aid = Column(ForeignKey("anime.mal_aid"), index=True)
    a_group = Column(VARCHAR(100), index=True)
    resolution = Column(INTEGER(10), index=True)
    ep = Column(INTEGER(10))
    size = Column(INTEGER(10))
    checked = Column(TINYINT(1), server_default=text("'0'"))

    anime = relationship("Anime")

    def __repr__(self):
        return (
            f"Feed entry: {self.title} ({self.date})\n[{self.a_group}] [{self.mal_aid}] - {self.ep},"
            f" {self.resolution}, {self.size}MiB, {self.checked}\n{self.description}"
        )


class ListStatus(Base):
    __tablename__ = "list_status"

    user_id = Column(ForeignKey("users.mal_uid"), primary_key=True, nullable=False)
    mal_aid = Column(BIGINT(20), primary_key=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    show_type = Column(
        ENUM("TV", "Movie", "OVA", "Special", "ONA", "Music", "Other", "Unknown")
    )
    status = Column(TINYINT(3), nullable=False)
    watched = Column(INTEGER(10))
    eps = Column(INTEGER(10))
    score = Column(INTEGER(10), index=True)
    airing = Column(TINYINT(3))

    users = relationship("Users")

    def __repr__(self):
        return (
            f"{self.user_id}: {self.title} ({self.mal_aid}) - {self.show_type}\n"
            f"Status: {self.status} {self.watched}/{self.eps}, score: {self.score}, "
            f"Airing: {self.airing}"
        )


class Users(Base):
    __tablename__ = "users"

    id = Column(BIGINT(20), nullable=False, primary_key=True)
    tg_nick = Column(String(50), index=True)
    tg_id = Column(BIGINT(20), unique=True)
    mal_nick = Column(VARCHAR(50), index=True)
    mal_uid = Column(BIGINT(20), unique=True)
    preferred_res = Column(INTEGER(11), nullable=False, server_default=text("'720'"))
    service = Column(Enum("MAL", "Anilist", "Other"))


class UsersXTracked(Base):
    __tablename__ = "users_x_tracked"

    user_id = Column(
        ForeignKey("users.id"), primary_key=True, nullable=False, index=True
    )
    mal_aid = Column(
        ForeignKey("anime.mal_aid"), primary_key=True, nullable=False, index=True
    )
    last_ep = Column(INTEGER(10), server_default=text("'0'"))
    a_group = Column(String(50), index=True)

    anime = relationship("Anime")
    users = relationship("Users")


class AnimeXSynonyms(Base):
    __tablename__ = "anime_x_synonyms"

    mal_aid = Column(ForeignKey("anime.mal_aid"), nullable=False, index=True)
    synonym = Column(String(255), primary_key=True)

    anime = relationship("Anime")


class AnimeXSeasons(Base):
    __tablename__ = "anime_x_seasons"

    mal_aid = Column(ForeignKey("anime.mal_aid"), nullable=False, index=True, primary_key=True)
    season = Column(String(20), primary_key=True, index=True)

    anime = relationship("Anime")


class TorrentFiles(Base):
    __tablename__ = "torrent_files"
    __table_args__ = (
        Index(
            "mal_aid", "mal_aid", "a_group", "episode", "res", "file_size", unique=True
        ),
    )

    mal_aid = Column(ForeignKey("anime.mal_aid"), nullable=False)
    a_group = Column(String(50), nullable=False)
    episode = Column(SMALLINT(5), nullable=False)
    torrent = Column(String(200), primary_key=True)
    res = Column(INTEGER(11))
    file_size = Column(INTEGER(10), nullable=False)


class GifTags(Base):
    __tablename__ = "gif_tags"
    __table_args__ = (Index("gif_tags_un", "media_id", "tag", unique=True),)

    id = Column(BIGINT(20), nullable=False, unique=True)
    media_id = Column(String(100), primary_key=True, nullable=False, index=True)
    tag = Column(String(50), primary_key=True, nullable=False, index=True)


class Quotes(Base):
    __tablename__ = "quotes"

    id = Column(BIGINT(20), primary_key=True, unique=True)
    keyword = Column(String(100), nullable=False, unique=True)
    content = Column(Text, nullable=False)
    markdown = Column(Enum("HTML", "MD"), index=True)
    added_at = Column(DateTime, index=True, server_default=text("CURRENT_TIMESTAMP"))
    author_id = Column(BIGINT(20), nullable=False)

    def __repr__(self):
        return f"quote #{self.id}, keyword: {self.keyword}\n{self.content}\nby {self.author_id} @ {self.added_at}"


t_anime_x_characters = Table(
    "anime_x_characters",
    metadata,
    Column("mal_aid", ForeignKey("anime.mal_aid"), primary_key=True, nullable=False),
    Column(
        "mal_cid", ForeignKey("characters.mal_cid"), primary_key=True, nullable=False
    ),
)


t_anime_x_genres = Table(
    "anime_x_genres",
    metadata,
    Column("mal_aid", ForeignKey("anime.mal_aid"), primary_key=True, nullable=False),
    Column(
        "mal_gid",
        ForeignKey("genres.mal_gid"),
        primary_key=True,
        nullable=False,
        index=True,
    ),
)


t_anime_x_licensors = Table(
    "anime_x_licensors",
    metadata,
    Column("mal_aid", ForeignKey("anime.mal_aid"), primary_key=True, nullable=False),
    Column(
        "name",
        ForeignKey("licensors.name"),
        primary_key=True,
        nullable=False,
        index=True,
    ),
)


t_anime_x_producers = Table(
    "anime_x_producers",
    metadata,
    Column("mal_aid", ForeignKey("anime.mal_aid"), primary_key=True, nullable=False),
    Column(
        "mal_pid",
        ForeignKey("producers.mal_pid"),
        primary_key=True,
        nullable=False,
        index=True,
    ),
)


t_anime_x_studios = Table(
    "anime_x_studios",
    metadata,
    Column("mal_aid", ForeignKey("anime.mal_aid"), primary_key=True, nullable=False),
    Column(
        "mal_sid",
        ForeignKey("studios.mal_sid"),
        primary_key=True,
        nullable=False,
        index=True,
    ),
)


v_last_episodes = Table(
    "last_episodes",
    metadata,
    Column("tg_id", BIGINT(20)),
    Column("torrent", String(200)),
    Column("episode", SMALLINT(5)),
    Column("mal_aid", BIGINT(20)),
    Column("id", BIGINT(20), server_default=text("'0'")),
    Column("a_group", String(50)),
    Column("res", INTEGER(11)),
)


v_today_titles = Table(
    "today_titles",
    metadata,
    Column("title", String(255)),
    Column("ftime", String(10)),
    Column("mal_aid", BIGINT(20)),
    Column("cnt", SMALLINT(5)),
)


v_pending_delivery = Table(
    "pending_delivery",
    metadata,
    Column("tg_id", BIGINT(20)),
    Column("torrent", String(200)),
    Column("episode", SMALLINT(5)),
    Column("mal_aid", BIGINT(20)),
    Column("id", BIGINT(20), server_default=text("'0'")),
    Column("a_group", String(50)),
    Column("res", INTEGER(11)),
)
