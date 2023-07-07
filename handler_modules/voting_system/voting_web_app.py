import json
import urllib.parse

from telegram import Update, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, TelegramError, \
    ChatMemberLeft
from telegram.ext import ContextTypes

import config
from handler_modules.base import Handler
from handler_modules.voting_system.exceptions import VotingIsFinishedError, InvalidVotesError
from handler_modules.voting_system.system import VotingSystem


class Vote(Handler):
    command = "vote"

    def answer(self, result):
        member = self.bot.get_chat_member(config.main_chat, self.user.id)
        if isinstance(member, ChatMemberLeft):
            self.message.reply_text(
                "Вы не являетесь членом нужного чата!"
            )
            return

        vs = VotingSystem.get_voting(self.bot_data)

        params = dict(stage=vs.stage)
        if votes := vs.user_votes.get(self.user.id):
            vote_string = "".join([str(int(vote)) for vote in votes])
            params["votes"] = vote_string
        if available_string := vs.get_current_available_string():
            params["available"] = available_string
        query_string = '?' + urllib.parse.urlencode(params)
        markup = ReplyKeyboardMarkup.from_button(
                KeyboardButton(
                    text="Проголосовать!",
                    web_app=WebAppInfo(url=f"https://gwellir.github.io/{query_string}"),
                )
            )
        markup.resize_keyboard = True
        self.message.reply_text(
            "Нажмите на кнопку ниже, чтобы перейти в WebApp для голосования.",
            reply_markup=markup
        )


class VotingWebApp(Handler):

    def __call__(self, update: Update, context: ContextTypes.context):
        member = context.bot.get_chat_member(config.main_chat, update.effective_user.id)
        if isinstance(member, ChatMemberLeft):
            update.effective_message.reply_text(
                "Вы не являетесь членом нужного чата!"
            )
            return

        vs = VotingSystem.get_voting(context.bot_data)
        if (not vs) or vs.is_finished:
            reply_text = "Это голосование закончено"

        else:
            data = json.loads(update.effective_message.web_app_data.data)
            print(update.effective_user.id, update.effective_user.username, data)
            stage = data.get("stage")
            boolean_data = [bool(int(char)) for char in data.get("votes")]
            if stage != vs.stage:
                reply_text = "Вы пытаетесь подать голоса из предыдущей стадии голосования"

            else:
                candidates = vs.get_current_round_candidates()
                results = "\n".join([
                    f"{candidate[0].get_name()} ({candidate[0].get_category()})"
                    for i, candidate in enumerate(candidates) if boolean_data[i]
                ])
                try:
                    vs.set_user_votes(update.effective_user.id, boolean_data)
                    reply_text = f"Вы ({update.effective_user.name}#{update.effective_user.id})" \
                                 f" проголосовали за:\n{results}"
                except VotingIsFinishedError:
                    reply_text = "Это голосование закончено"
                except InvalidVotesError:
                    reply_text = "Некорректный набор голосов (возможно, Вы пытаетесь проголосовать с двух разных сессий Telegram?)"
        update.effective_message.reply_text(
            reply_text,
            reply_markup=ReplyKeyboardRemove(),
        )
