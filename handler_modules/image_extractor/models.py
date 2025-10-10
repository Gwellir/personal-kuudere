from __future__ import annotations

import logging

from enum import Enum

from pydantic import BaseModel
from pydantic._internal import _repr
from strip_tags import strip_tags

logger = logging.getLogger("handler.extract_images.models")


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"


class PostMedia(BaseModel):
    url: str
    type: MediaType
    downloaded: bytes | None = None

    def __repr_args__(self) -> _repr.ReprArgs:
        return ("url", self.url), ("type", str(self.type)), ("downloaded", self.downloaded if not self.downloaded else f"{len(self.downloaded)} bytes")


class PostData(BaseModel):
    url: str
    text: str | None = ""
    attached_media: list[PostMedia] = []
    id: str
    name: str | None = ""
    qrt: PostData | None = None

    def get_caption(self, original: str, author: str):
        prefix = (
            'Медиа из {qrt}<a href="{url}">поста</a> {name}\n'.format(
                url=self.url,
                name=self.name,
                qrt="QRT " if self.qrt and self.attached_media == self.qrt.attached_media else "",
            )
        )
        prefix += '<a href="{original}">&gt; сообщение от {author} &lt;</a>'.format(
            original=original,
            author=author,
        )

        main_text = strip_tags(self.text).replace("<", "&lt;").replace(">", "&gt;")
        # or shorten the text from vk if it's too long
        if len(main_text) >= (
            remainder_len := 1024 - len(strip_tags(prefix))
        ):
            main_text = main_text[: remainder_len - 8] + " &lt;...&gt;"

        if self.qrt:
            full_text = main_text
            qrt_prefix = f"\n\n<code>---------------------------</code>\n<i><a href='{self.qrt.url}'>QRT</a> ({self.qrt.name}):</i>\n\n"
            qrt_text = self.qrt.text
            full_text += (f"{qrt_prefix}{qrt_text}")
            if len(full_text) >= (
                remainder_len := 1024 - len(strip_tags(qrt_prefix)) - len(strip_tags(prefix))
            ):
                remainder_len = 400
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