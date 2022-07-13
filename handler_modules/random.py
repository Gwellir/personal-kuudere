import argparse
from random import choice as rand_choice
from random import shuffle

from sqlalchemy import func
from telegram import ParseMode

from orm.ORMWrapper import Anime, Genres, ListStatus, Users, t_anime_x_genres
from utils.db_wrapper2 import DataInterface

from .base import Handler, HandlerError

HELP_MSG = (
    "Использование:\n<code>/random [-t type1* type2*...] [-g genre1* genre2*...] [-r rating X [Y]]</code>"
    " - случайное аниме из вашего PTW, фильтры по жанрам, типу, рейтингу на MAL, либо\n"
    "<code>/random [-s X [Y]] [-u user1 user2...] [-t type1* type2*...] [-g genre1* genre2*...] [-r rating X [Y]]</code> - "
    "случайная рекомендация с оценкой из интервала X-Y из списков пользователей бота"
    "(фильтры по оценке, пользователям, жанрам, типу, рейтингу на MAL).\n\n"
    "<code>*типы - TV, Movie, OVA, ONA, Special, Music, Unknown, Other</code>"
)
ALL_TYPES = ["tv", "ova", "movie", "ona", "special", "unknown", "music", "other"]
STATUS_DICT = {
    "current": 1,
    "ongoing": 1,
    "watching": 1,
    "ong": 1,
    "completed": 2,
    "complete": 2,
    "done": 2,
    "paused": 3,
    "onhold": 3,
    "hold": 3,
    "on-hold": 3,
    "dropped": 4,
    "drop": 4,
    "planned": 6,
    "ptw": 6,
}


class AnimeSelector(Handler):
    command = "random"

    def __init__(self, di=None):
        super().__init__()
        self.own_list = True
        self.pool = 0
        self.session = self.br.get_session()
        self.di = di if di else DataInterface(self.br)

        self.query = None
        self.params = None

    def _parse_random_command(self, opts):
        parser = argparse.ArgumentParser(
            description="Get random anime from stored userlists.",
            add_help=False,
            # exit_on_error=False,
        )
        group_score = parser.add_argument_group()
        group_score.add_argument("-s", "--score", nargs="+", type=int)
        parser.add_argument("-?", "--help", action="store_true")
        parser.add_argument("-u", "--users", nargs="+")
        parser.add_argument("-t", "--types", nargs="+")
        parser.add_argument("-g", "--genres", nargs="+")
        parser.add_argument("-c", "--condition", nargs="+")
        parser.add_argument("-r", "--rating", nargs="+", type=float)

        parsed, unknown = parser.parse_known_args(opts)
        if unknown:
            err_str = ", ".join(unknown)
            raise HandlerError(f"Неизвестные аргументы: {err_str}")

        return parsed

    def parse(self, args: list):
        if (self.user.id,) not in self.di.select_user_tg_ids().all():
            raise HandlerError(
                "Вы не зарегистрированы на боте, используйте /reg в моём привате!"
            )

        self.params = self._parse_random_command(args)
        if self.params.users:
            self.params.users = [user.lower() for user in self.params.users]
        if self.params.genres:
            self.params.genres = [genre.lower() for genre in self.params.genres]
        return self.params

    def _apply_user_filter(self, users):
        if users:
            registered_users = (
                self.session.query(Users)
                .filter(Users.tg_nick != None, Users.tg_nick.in_(users))
                .with_entities(Users.tg_nick)
            )
            registered_users_list = [
                entry[0].lower() for entry in registered_users.all()
            ]
            wrong_users = set(users) - set(registered_users_list)
            if wrong_users:
                users_str = ", ".join(wrong_users)
                raise HandlerError(
                    f"Указаны несуществующие пользователи: <code>{users_str}</code>\n"
                    f"Проверьте, что используется ник из Telegram, и cоответствующий пользователь"
                    f" зарегистрирован на боте!"
                )

            users = registered_users_list
            self.query = self.query.filter(Users.tg_nick.in_(registered_users))

    def _apply_score_filter(self, score):
        if not score:
            return
        if len(score) == 1:
            score.append(score[0])
        if score[0] not in range(0, 11) or score[1] not in range(0, 11):
            raise HandlerError("Оценка должна быть в диапазоне от 0 (нет оценки) до 10")
        else:
            self.query = self.query.filter(
                ListStatus.score >= score[0], ListStatus.score <= score[1]
            )

    def _apply_type_filter(self, types):
        if types:
            self.params.types = [entry for entry in types if entry.lower() in ALL_TYPES]
            self.query = self.query.filter(ListStatus.show_type.in_(types))

    def _apply_status_filter(self, statuses):
        if statuses:
            self.params.condition = [
                entry for entry in statuses if entry.lower() in STATUS_DICT.keys()
            ]
            status_values = [STATUS_DICT[entry] for entry in self.params.condition]
            self.query = self.query.filter(ListStatus.status.in_(status_values))

    def _apply_genre_filter(self, genres, query):
        if genres:
            mal_genres = [
                entry[0].lower() for entry in self.session.query(Genres.name).all()
            ]
            wrong_genres = set(genres) - set(mal_genres)
            if wrong_genres:
                genres_str = ", ".join(wrong_genres)
                raise HandlerError(
                    f"Указаны несуществующие жанры: <code>{genres_str}</code>"
                )
            query = (
                query.join(t_anime_x_genres)
                .join(Genres)
                .filter(Genres.name.in_(genres))
                .group_by(Anime.mal_aid)
                .having(func.count(Anime.mal_aid) == len(genres))
            )

        return query

    def _apply_rating_filter(self, rating, query):
        if not rating:
            return query
        if len(rating) == 1:
            rating.append(rating[0])
        if not 1 <= rating[0] <= 10 or not 1 <= rating[1] <= 10:
            raise HandlerError("Рейтинг аниме должен быть в диапазоне от 1 до 10")
        else:
            query = query.filter(Anime.score >= rating[0], Anime.score <= rating[1])

        return query

    def process(self, params):
        if params.help:
            return None
        # anime_id_list = [entry[0] for entry in self.query.with_entities(Anime.mal_aid).all()]
        self.query = (
            self.session.query(ListStatus)
            .join(Users, ListStatus.user_id == Users.mal_uid)
            .filter(ListStatus.airing == 2)
        )  # finished
        if params.rating or params.genres:
            anime_query = self.session.query(Anime)
            anime_query = self._apply_rating_filter(params.rating, anime_query)
            if params.genres:
                params.genres = [" ".join(genre.split("_")) for genre in params.genres]
                anime_query = self._apply_genre_filter(params.genres, anime_query)
            self.query = self.query.filter(
                ListStatus.mal_aid.in_(anime_query.with_entities(Anime.mal_aid))
            )
        if not params.score and not params.users and not params.condition:
            self.query = self.query.filter(
                Users.tg_id == self.user.id, ListStatus.status == 6
            )
        else:
            self.own_list = False
            own_aids_query = []
            # todo separate into check_force_own or something
            if not self.params.users or (
                self.user.username.lower() not in self.params.users
            ):
                own_aids_query = self.query.filter(
                    Users.tg_id == self.user.id, ListStatus.status != 6
                ).with_entities(ListStatus.mal_aid)
            self.query = self.query.filter(
                ListStatus.status != 6, ListStatus.mal_aid.notin_(own_aids_query)
            )
            self._apply_user_filter(params.users)
            self._apply_score_filter(params.score)
            self._apply_status_filter(params.condition)
        self._apply_type_filter(params.types)
        result = self.query.all()
        self.pool = len(result)

        return self.query.all()

    def answer(self, result):
        entry = rand_choice(result) if result else None
        if self.params.help:
            msg = (
                "Выбор случайного аниме из списков пользователей:\n\n"
                "Формат: <code>/random [-param value(s)] ...</code>\n"
                "Поддерживаются параметры:\n"
                "<code>-t type1[ type2 ...]</code> - типы аниме (movie, TV, OVA...)\n"
                "<code>-r X [Y]</code> - оценка на MAL от Х до Х [до Y]\n"
                "<code>-g genre1[ genre2 ...]</code> - набор интересующих жанров\n"
                "<i>(Следующие параметры запускают поиск в чужих списках):</i>\n"
                "<code>-s X [Y]</code> - оценка (другого пользователя) от X до Х [до Y]\n"
                "<code>-u user1[ user2 ...]</code> - имена пользователей, из списков которых делается выборка\n"
                "<code>-c cond1[ cond2 ...]</code> - интересующие состояния просмотра (hold, ongoing, drop...)"
            )
        elif self.own_list:
            msg = "Случайное аниме из PTW:\n\n"
            msg += (
                f'<a href="https://myanimelist.net/anime/{entry.mal_aid}">{entry.title}</a>'
                f' ({entry.show_type}{" - %s эп." % entry.eps if entry.eps > 1 else ""})'
                if entry
                else "в PTW не найдено тайтлов"
            )
        else:
            sep = ", "
            msg = f"<b>Случайное аниме из сохранённых списков</b>:\n"
            msg += (
                f"<b>пользователи</b>: {sep.join(self.params.users)}\n"
                if self.params.users
                else ""
            )
            msg += (
                f"<b>тип</b>: {sep.join(self.params.types)}\n"
                if self.params.types
                else ""
            )
            msg += (
                f"<b>жанры</b>: {sep.join(self.params.genres)}\n"
                if self.params.genres
                else ""
            )
            msg += (
                f"<b>статус</b>: {sep.join(self.params.condition)}\n"
                if self.params.condition
                else ""
            )

            if self.params.score:
                msg += (
                    f"<b>оценка</b>: [{self.params.score[0]}-{self.params.score[1]}]\n"
                    if self.params.score[0] != self.params.score[1]
                    else f"<b>оценка</b>: [{self.params.score[0]}]\n"
                )
            if self.params.rating:
                msg += (
                    f"<b>рейтинг</b>: [{self.params.rating[0]}-{self.params.rating[1]}]\n"
                    if self.params.rating[0] != self.params.rating[1]
                    else f"<b>рейтинг</b>: [{self.params.rating[0]}]\n"
                )
            msg += (
                f'\n<a href="https://myanimelist.net/anime/{entry.mal_aid}">{entry.title}</a>'
                f' ({entry.show_type}{" - %s эп." % entry.eps if entry.eps > 1 else ""})'
                f" - {entry.users.tg_nick} ({entry.score})"
                if entry
                else "в списках не найдено подходящих тайтлов"
            )

        self.bot.send_message(
            chat_id=self.chat.id,
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=self.message.message_id,
        )
        self.session.close()


class AnimeFilter(AnimeSelector):
    amount = 10
    command = "filter"

    def answer(self, result: list):
        if result:
            shuffle(result)
            result = result[: self.amount]
        sep = ", "
        if self.own_list:
            msg = f"<b>Случайное аниме из PTW</b> ({min(self.amount, len(result))} из {self.pool}):\n\n"
            msg += (
                f"<b>тип</b>: {sep.join(self.params.types)}\n"
                if self.params.types
                else ""
            )
            msg += (
                f"<b>жанры</b>: {sep.join(self.params.genres)}\n"
                if self.params.genres
                else ""
            )
            if self.params.rating:
                msg += (
                    f"<b>рейтинг</b>: [{self.params.rating[0]}-{self.params.rating[1]}]\n"
                    if self.params.rating[0] != self.params.rating[1]
                    else f"<b>рейтинг</b>: [{self.params.rating[0]}]\n"
                )
            for entry in result:
                msg += (
                    f'\n<a href="https://myanimelist.net/anime/{entry.mal_aid}">{entry.title}</a>'
                    f' ({entry.show_type}{" - %s эп." % entry.eps if entry.eps > 1 else ""})'
                )
            if not result:
                msg += "в PTW не найдено тайтлов"
        else:
            msg = f"<b>Случайное аниме из сохранённых списков</b> ({min(self.amount, len(result))} из {self.pool}):\n"
            msg += (
                f"<b>пользователи</b>: {sep.join(self.params.users)}\n"
                if self.params.users
                else ""
            )
            msg += (
                f"<b>тип</b>: {sep.join(self.params.types)}\n"
                if self.params.types
                else ""
            )
            msg += (
                f"<b>жанры</b>: {sep.join(self.params.genres)}\n"
                if self.params.genres
                else ""
            )
            msg += (
                f"<b>статус</b>: {sep.join(self.params.condition)}\n"
                if self.params.condition
                else ""
            )

            if self.params.score:
                msg += (
                    f"<b>оценка</b>: [{self.params.score[0]}-{self.params.score[1]}]\n"
                    if self.params.score[0] != self.params.score[1]
                    else f"<b>оценка</b>: [{self.params.score[0]}]\n"
                )
            if self.params.rating:
                msg += (
                    f"<b>рейтинг</b>: [{self.params.rating[0]}-{self.params.rating[1]}]\n"
                    if self.params.rating[0] != self.params.rating[1]
                    else f"<b>рейтинг</b>: [{self.params.rating[0]}]\n"
                )
            for entry in result:
                msg += (
                    f'\n<a href="https://myanimelist.net/anime/{entry.mal_aid}">{entry.title}</a>'
                    f' ({entry.show_type}{" - %s эп." % entry.eps if entry.eps > 1 else ""})'
                    f" - {entry.users.tg_nick} ({entry.score})"
                )
            if not result:
                msg += "в списках не найдено подходящих тайтлов"

        self.bot.send_message(
            chat_id=self.chat.id,
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=self.message.message_id,
        )
        self.session.close()
