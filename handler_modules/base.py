import abc


class Handler:
    command = None

    def __init__(self, base_relations):
        self.br = base_relations
        self.session = self.br.session

    def __call__(self, update, context):
        self.bot = context.bot
        self.message = update.effective_message
        self.chat = update.effective_chat
        self.user = update.effective_user

        params = self.parse(context.args)
        result = self.process(params)
        self.act(result)

    @abc.abstractmethod
    def parse(self, args: list):
        pass

    @abc.abstractmethod
    def process(self, params: list):
        pass

    @abc.abstractmethod
    def act(self, result):
        pass


class Start(Handler):
    command = 'start'

    def __call__(self, update, context):
        self.act(None)

    def act(self, result):
        self.bot.send_message(chat_id=self.chat.id,
                              text="Бот некоторого аниме-чатика, для регистрации в привате бота введите /reg или /register")
