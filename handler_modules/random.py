import argparse
from pprint import pprint
from random import choice as rand_choice

from sqlalchemy import func
from telegram import ParseMode

from .base import Handler, HandlerError
from orm.ORMWrapper import Users, ListStatus, Anime, Genres, t_anime_x_genres
from utils.db_wrapper2 import DataInterface


HELP_MSG = 'Использование:\n<code>/random</code> - случайное аниме из вашего PTW, либо\n' \
            '<code>/random [-s X [Y]] [-u user1 user2...] [-t type1* type2*...]</code> - ' \
            'случайная рекомендация с оценкой из интервала X-Y из списков пользователей бота.\n' \
            '<code>/random [-u user1 user2...] [-t type1* type2*...]</code> - ' \
            'случайная рекомендация из списков PTW пользователей бота.\n\n' \
            '<code>*типы - TV, Movie, OVA, ONA, Special, Music, Unknown, Other</code>'
ALL_TYPES = ['tv', 'ova', 'movie', 'ona', 'special', 'unknown', 'music', 'other']


class AnimeSelector(Handler):
    command = 'random'

    def __init__(self, di=None):
        super().__init__()
        self._own_list = True
        self.session = self.br.get_session()
        if not di:
            self.di = DataInterface(self.br)
        else:
            self.di = di

        self.query = None
        self.params = None

    def _parse_random_command(self, opts):
        parser = argparse.ArgumentParser(
            description='Get random anime from stored userlists.',
            # exit_on_error=False,
        )
        group_score = parser.add_argument_group()
        group_score.add_argument('-s', '--score', nargs='+', type=int)
        parser.add_argument('-u', '--users', nargs='+')
        parser.add_argument('-t', '--types', nargs='+')
        parser.add_argument('-g', '--genres', nargs='+')
        parser.add_argument('-r', '--rating', nargs='+', type=float)

        parsed = None
        try:
            parsed = parser.parse_args(opts)
        except argparse.ArgumentError as err:
            raise HandlerError(HELP_MSG)

        return parsed

    def parse(self, args: list):
        if (self.user.id,) not in self.di.select_user_tg_ids().all():
            raise HandlerError('Вы не зарегистрированы на боте, используйте /reg в моём привате!')

        self.params = self._parse_random_command(args)
        return self.params

    def _apply_user_filter(self, users):
        if users:
            self.params.users = [entry for entry in users if (entry,) in self.di.select_registered_user_nicks().all()]
            self.query = self.query.filter(Users.tg_nick.in_(users))

    def _apply_score_filter(self, score):
        if not score:
            return
        if len(score) == 1:
            score.append(score[0])
        if score[0] not in range(1, 11) or score[1] not in range(1, 11):
            raise HandlerError('Оценка должна быть в диапазоне от 1 до 10')
        else:
            self.query = self.query.filter(ListStatus.score >= score[0], ListStatus.score <= score[1])

    def _apply_type_filter(self, types):
        if types:
            self.params.types = [entry for entry in types if entry.lower() in ALL_TYPES]
            self.query = self.query.filter(ListStatus.show_type.in_(types))

    def _apply_genre_filter(self, genres, query):
        if genres:
            query = query.join(t_anime_x_genres).join(Genres).\
            filter(Genres.name.in_(genres)).group_by(Anime.mal_aid).having(func.count(Anime.mal_aid) == len(genres))

        return query

    def _apply_rating_filter(self, rating, query):
        if not rating:
            return query
        if len(rating) == 1:
            rating.append(rating[0])
        if rating[0] not in range(1, 11) or rating[1] not in range(1, 11):
            raise HandlerError('Рейтинг аниме должен быть в диапазоне от 1 до 10')
        else:
            query = query.filter(Anime.score >= rating[0], Anime.score <= rating[1])

        return query

    def process(self, params):
        anime_query = self.session.query(Anime)
        anime_query = self._apply_genre_filter(params.genres, anime_query)
        anime_query = self._apply_rating_filter(params.rating, anime_query)
        # anime_id_list = [entry[0] for entry in self.query.with_entities(Anime.mal_aid).all()]
        self.query = self.session.query(ListStatus). \
            join(Users, ListStatus.user_id == Users.mal_uid). \
            filter(ListStatus.airing == 2)  # finished
        if params.rating or params.genres:
            self.query = self.query.filter(ListStatus.mal_aid.in_(anime_query.with_entities(Anime.mal_aid)))
        if not params.score and not params.users:
            self.query = self.query.filter(Users.tg_id == self.user.id,
                                           ListStatus.status == 6)
        else:
            self._own_list = False
            self.query = self.query.filter(ListStatus.status != 6, ListStatus.airing )
            self._apply_user_filter(params.users)
            self._apply_score_filter(params.score)
        self._apply_type_filter(params.types)
        result = self.query.all()
        self.session.close()

        return result

    def answer(self, result):
        entry = rand_choice(result) if result else None
        if self._own_list:
            msg = 'Случайное аниме из PTW:\n\n'
            msg += f'<a href="https://myanimelist.net/anime/{entry.mal_aid}">{entry.title}</a>' \
                   f' ({entry.show_type}{" - %s эп." % entry.eps if entry.eps > 1 else ""})'\
                if entry else 'в PTW не найдено тайтлов'
        else:
            sep = ', '
            msg = f'<b>Случайное аниме из сохранённых списков</b>:\n'
            msg += f'<b>пользователи</b>: {sep.join(self.params.users)}\n' if self.params.users else ''
            msg += f'<b>тип</b>: {sep.join(self.params.types)}\n' if self.params.types else ''
            msg += f'<b>тип</b>: {sep.join(self.params.genres)}\n' if self.params.genres else ''

            if self.params.score:
                msg += f'<b>оценка</b>: [{self.params.score[0]}-{self.params.score[1]}]\n\n' \
                    if self.params.score[0] != self.params.score[1] \
                    else f'<b>оценка</b>: [{self.params.score[0]}]\n\n'
            if self.params.rating:
                msg += f'<b>рейтинг</b>: [{self.params.rating[0]}-{self.params.rating[1]}]\n\n' \
                    if self.params.rating[0] != self.params.rating[1] \
                    else f'<b>рейтинг</b>: [{self.params.rating[0]}]\n\n'
            msg += f'<a href="https://myanimelist.net/anime/{entry.mal_aid}">{entry.title}</a>' \
                   f' ({entry.show_type}{" - %s эп." % entry.eps if entry.eps > 1 else ""})' \
                   f' - {entry.users.tg_nick} ({entry.score})' \
                if entry else 'в списках не найдено подходящих тайтлов'

        self.bot.send_message(chat_id=self.chat.id, text=msg, parse_mode=ParseMode.HTML)
