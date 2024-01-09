import abc
import logging
from typing import TYPE_CHECKING

from telegram import ParseMode

from orm.ORMWrapper import BaseRelations

if TYPE_CHECKING:
    from telegram import Bot, Chat, Message, Update, User


logger = logging.getLogger("base_handler")


class HandlerError(Exception):
    def __init__(self, error_msg):
        self._error_msg = error_msg

    def __str__(self):
        return f"{self._error_msg}"


class Handler:
    command = None
    answer_template: str = None

    def __init__(self):
        self.br = BaseRelations()
        # self.session = self.br.session

    def __call__(self, update: "Update", context):
        self.bot: Bot = context.bot
        self.bot_data = context.bot_data
        self.message: Message = update.effective_message
        self.chat: Chat = update.effective_chat
        self.user: User = update.effective_user

        self._run(context.args)

    def _run(self, args):
        logger.info(f"started handler for: {self.command}")
        try:
            logger.info(f"received args: {args}")
            params = self.parse(args)
            logger.info(f"parsed params: {params}")
            result = self.process(params)
            logger.info(f"final result: {result}")
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
        return self.bot.send_message(chat_id=self.chat.id, text=result)


class Start(Handler):
    command = "start"

    def __call__(self, update, context):
        self.answer(None)

    def answer(self, result):
        self.bot.send_message(
            chat_id=self.chat.id,
            text="Бот некоторого аниме-чатика, для регистрации в привате бота введите /reg или /register",
        )
