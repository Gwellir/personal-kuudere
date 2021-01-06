import abc
from orm.ORMWrapper import BaseRelations


class Handler:
    command = None

    def __init__(self):
        self.br = BaseRelations()
        # self.session = self.br.session

    def __call__(self, update, context):
        self.bot = context.bot
        self.message = update.effective_message
        self.chat = update.effective_chat
        self.user = update.effective_user

        params = self.parse(context.args)
        result = self.process(params)
        self.answer(result)

    @abc.abstractmethod
    def parse(self, args: list):
        pass

    @abc.abstractmethod
    def process(self, params: list):
        pass

    @abc.abstractmethod
    def answer(self, result):
        self.bot.send_message(chat_id=self.chat.id, text=result)


class Start(Handler):
    command = 'start'

    def __call__(self, update, context):
        self.answer(None)

    def answer(self, result):
        self.bot.send_message(chat_id=self.chat.id,
                              text="Бот некоторого аниме-чатика, для регистрации в привате бота введите /reg или /register")
