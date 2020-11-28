from .base import Handler
from orm.ORMWrapper import ListStatus, Users


TYPE_LIST = ['TV', 'ONA']


class UsersStats(Handler):
    command = 'users'

    def select_users_with_ongoing_titles_in_list(self):
        return self.session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id)\
            .filter(ListStatus.status == 1, ListStatus.airing == 1)\
            .filter(ListStatus.show_type.in_(TYPE_LIST))\
            .with_entities(Users.mal_nick).distinct()

    def select_users_with_any_titles_in_list(self):
        return self.session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id)\
            .with_entities(Users.mal_nick, Users.tg_nick).distinct()

    def parse(self, args):
        return args

    def process(self, params):
        if len(params) > 0 and params[0] == 'season':
            users = '\n'.join([u[0] for u in
                               self.select_users_with_ongoing_titles_in_list().all()])
            msg = f'Активные пользователи:\n{users}'
        else:
            users = '\n'.join([f'{u[1]} - {u[0]}' for u in
                               self.select_users_with_any_titles_in_list().all()])
            msg = f'Список пользователей:\n{users}'
        return msg

    def act(self, result):
        self.bot.send_message(chat_id=self.chat.id, text=result)
