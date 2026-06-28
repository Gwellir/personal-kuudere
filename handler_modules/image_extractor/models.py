from __future__ import annotations

import logging

from enum import Enum

from pydantic import BaseModel
from pydantic._internal import _repr
from strip_tags import strip_tags

logger = logging.getLogger("handler.extract_images.models")

MAX_LENGTH = 1024

class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"


class PostMedia(BaseModel):
    url: str
    type: MediaType
    downloaded: bytes | None = None

    def __repr_args__(self) -> _repr.ReprArgs:
        return (
            ("url", self.url),
            ("type", str(self.type)),
            (
                "downloaded",
                (
                    self.downloaded
                    if not self.downloaded
                    else f"{len(self.downloaded)} bytes"
                ),
            ),
        )


class TranslationData(BaseModel):
    destination_language: str
    source_language: str
    text: str = ""


class PostData(BaseModel):
    url: str
    text: str | None = ""
    attached_media: list[PostMedia] = []
    id: str
    name: str | None = ""
    qrt: PostData | None = None
    language: str | None = None
    translated: TranslationData | None = None

    @staticmethod
    def _format_translation(post_data: "PostData") -> str:
        return f"TL: {post_data.language.upper()}\n\n{post_data.translated.text}"

    def get_caption(self, original: str, author: str, length_limit: int = MAX_LENGTH) -> str:
        prefix = 'Медиа из {qrt}<a href="{url}">поста</a> {name}\n'.format(
            url=self.url,
            name=self.name,
            qrt=(
                "QRT "
                if self.qrt and self.attached_media == self.qrt.attached_media
                else ""
            ),
        )
        
        prefix += '<a href="{original}">&gt; сообщение от {author} &lt;</a>'.format(
            original=original,
            author=author,
        ) if original else '&gt; сообщение от {author} &lt;'.format(author=author)
        
        to_translate_post = not (self.language in ["ru", "en"] or not self.language) and self.translated
        self.text = strip_tags(self.text).replace("<", "&lt;").replace(">", "&gt;")
        main_text = (
            self._format_translation(self)
            if to_translate_post
            else self.text
        )
        # or shorten the text from vk if it's too long
        if len(main_text) >= (
            remainder_len := length_limit - len(strip_tags(prefix))
        ):
            main_text = main_text[: remainder_len - 8] + " &lt;...&gt;"

        if self.qrt:
            full_text = main_text
            qrt_prefix = f'\n\n<code>------------------</code>\n<i><a href="{self.qrt.url}">QRT</a> ({self.qrt.name}):</i>\n\n'
            to_translate_qrt = not (self.qrt.language in ["ru", "en"] or not self.qrt.language) and self.qrt.translated
            qrt_text = ( 
                self._format_translation(self.qrt)
                if to_translate_qrt
                else self.qrt.text
            )
            full_text += (f"{qrt_prefix}{qrt_text}")
            if len(full_text) >= (
                remainder_len := length_limit - len(strip_tags(qrt_prefix)) - len(strip_tags(prefix))
            ):
                remainder_len = length_limit // 2
                main_text = main_text[:remainder_len] + " &lt;...&gt;"
                qrt_text = qrt_text[:remainder_len] + " &lt;...&gt;"
                text = f"{main_text}{qrt_prefix}{qrt_text}"
            else:
                text = full_text
        else:
            text = main_text

        caption = "{prefix}\n\n{text}".format(
            prefix=prefix,
            text=text,
        )

        logger.debug(f"Caption length: {len(strip_tags(caption))}")

        return caption
