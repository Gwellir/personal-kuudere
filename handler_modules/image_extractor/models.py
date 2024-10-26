from enum import Enum
from typing import ForwardRef

from pydantic import BaseModel
from strip_tags import strip_tags


PostData = ForwardRef("PostData")


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"


class PostMedia(BaseModel):
    url: str
    type: MediaType


class PostData(BaseModel):
    url: str
    text: str | None = ""
    attached_media: list[PostMedia] = []
    id: str
    name: str | None = ""
    qrt: PostData | None = None

    def __str__(self):
        prefix = (
            'Медиа из {qrt}<a href="{url}">поста</a> {name}\n'.format(
                url=self.url,
                name=self.name,
                qrt="QRT " if self.attached_media == self.qrt.attached_media else "",
            )
        )
        prefix += '<a href="{original}">&gt; сообщение от {author} &lt;</a>'

        text = strip_tags(self.text).replace("<", "&lt;").replace(">", "&gt;")
        # or shorten the text from vk if it's too long
        if len(text) >= (
            remainder_len := 1024 - len(strip_tags(prefix))
        ):
            text = text[: remainder_len - 8] + " &lt;...&gt;"

        if self.qrt:
            text += (f"\n\n<code>---------------------------</code>"
                     f"\n<i><a href='{self.qrt.url}'>QRT</a> ({self.qrt.name}):</i>"
                     f"\n\n{self.qrt.text}")

        return "{prefix}\n\n{text}".format(
            prefix=prefix,
            text=text,
        )

    get_caption = __str__