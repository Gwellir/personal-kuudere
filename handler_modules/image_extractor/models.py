from enum import Enum

from pydantic import BaseModel


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"


class PostMedia(BaseModel):
    url: str
    type: MediaType


class PostData(BaseModel):
    url: str
    text: str | None = ""
    attached_media: list[PostMedia] = []
    id: str
    name: str | None = ""
