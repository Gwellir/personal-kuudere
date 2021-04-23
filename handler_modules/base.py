import abc

from telegram import ParseMode

from orm.ORMWrapper import BaseRelations


class HandlerError(Exception):
    def __init__(self, error_msg):
        self._error_msg = error_msg

    def __str__(self):
        return f"{self._error_msg}"


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

        self._run(context.args)

    def _run(self, args):
        try:
            params = self.parse(args)
            result = self.process(params)
            self.answer(result)
        except HandlerError as err:
            self.bot.send_message(
                chat_id=self.chat.id,
                text=f"Ошибка!\n{err}",
                parse_mode=ParseMode.HTML,
                reply_to_message_id=self.message.message_id,
            )

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
    command = "start"

    def __call__(self, update, context):
        self.answer(None)

    def answer(self, result):
        self.bot.send_message(
            chat_id=self.chat.id,
            text="Бот некоторого аниме-чатика, для регистрации в привате бота введите /reg или /register",
        )
