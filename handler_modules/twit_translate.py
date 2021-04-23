import re

from googletrans import Translator

from .base import Handler


class TwitTranslate(Handler):
    command = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tl = Translator()

    def _get_status_content(self):
        pass

    def parse(self, args):
        return []

    def process(self, params: list):
        entities = self.message.parse_entities()
        for entity, text in entities.items():
            status = re.findall(r"https://twitter.com/\w+/status/(\d+)", text)
            if len(status):
                content = self._get_status_content(status)
                ru_content = self.tl.translate(content, src="jp", dest="ru")
        return ru_content
