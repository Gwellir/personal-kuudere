import io
import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from time import sleep
from typing import Literal

import requests
from PIL import Image, ImageDraw, ImageFont
from requests import Response

logger = logging.getLogger("handler.create_picture")

VOTING_NAME = "Осень 2024"

CHAR_IMAGE_CUT_PART = 0.8

TITLE_TUPLES = (
    ("MF Ghost 2nd Season", 960, "Sena Moroboshi", "https://cdn.myanimelist.net/images/characters/9/524884.jpg"),
    ("Nageki no Bourei wa Intai shitai", 939, "Tino Shade",
     "https://cdn.myanimelist.net/images/characters/14/573244.jpg"),
    ("Dandadan", 940, "Momo Ayase", "https://cdn.myanimelist.net/images/characters/7/562295.jpg"),
    ("Dandadan", 941, "Ken Takakura", "https://cdn.myanimelist.net/images/characters/5/531081.jpg"),
    ("Dandadan", 942, "Aira Shiratori", "https://cdn.myanimelist.net/images/characters/6/554080.jpg"),
    ("Dandadan", 943, "Rokuro", "https://cdn.myanimelist.net/images/characters/8/531083.jpg"),
    ("Ao no Hako", 944, "Taiki Inomata", "https://cdn.myanimelist.net/images/characters/7/543178.jpg"),
    ("Ao no Hako", 945, "Hina Chouno", "https://cdn.myanimelist.net/images/characters/11/574759.jpg"),
    ("Chi. Chikyuu no Undou ni Tsuite", 946, "Rafal", "https://cdn.myanimelist.net/images/characters/10/564208.jpg"),
    ("NegaPosi Angler", 947, "Hana Ayukawa", "https://cdn.myanimelist.net/images/characters/7/567572.jpg"),
    ("NegaPosi Angler", 948, "Debt Collector Boss", "https://cdn.myanimelist.net/images/characters/14/570351.jpg"),
    ("NegaPosi Angler", 949, "Fujishiro", "https://cdn.myanimelist.net/images/characters/7/559606.jpg"),
    ("Acro Trip", 950, "Mashirou Mashima", "https://cdn.myanimelist.net/images/characters/4/536724.jpg"),
    ("Acro Trip", 951, "Chroma Kurozane", "https://cdn.myanimelist.net/images/characters/6/536727.jpg"),
    ("Acro Trip", 952, "Kuma Kaijin", "https://cdn.myanimelist.net/images/characters/6/560694.jpg"),
    ("Acro Trip", 953, "Suikyou Date", "https://cdn.myanimelist.net/images/characters/2/560693.jpg"),
    ("Acro Trip", 954, "Kaju Noichigo", "https://cdn.myanimelist.net/images/characters/9/556694.jpg"),
    ("Puniru wa Kawaii Slime", 955, "Puniru", "https://cdn.myanimelist.net/images/characters/12/555935.jpg"),
    ("2.5-jigen no Ririsa", 956, "Masamune Okumura", "https://cdn.myanimelist.net/images/characters/9/563384.jpg"),
    ("2.5-jigen no Ririsa", 957, "Noa", "https://cdn.myanimelist.net/images/characters/3/547206.jpg"),
    ("2.5-jigen no Ririsa", 958, "Mayuri Hanyuu", "https://cdn.myanimelist.net/images/characters/3/560709.jpg"),
    ("2.5-jigen no Ririsa", 959, "Ririsa Amano", "https://cdn.myanimelist.net/images/characters/7/558255.jpg"),
)

FONT_BASIC = "arial.ttf"
FONT_HEADER = "Gabriola.ttf"
FONT_HEADER_SIZE = 50
FONT_TITLE_SIZE = 20
FONT_CHAR_SIZE = 14

AVATAR_H_SIZE = 86
CHAR_NAMEPLATE_HEIGHT = 48
TITLE_NAMEPLATE_HEIGHT = 40
TITLE_CARD_WIDTH = 570

CARD_H_AMOUNT = 6
MARGIN_VERTICAL = 4
MARGIN_HORIZONTAL = 2
COLUMN_COUNT = 3
BG_COLOR = "darkgray"
VOTING_HEADER_COLOR = (200, 50, 50, 255)
TITLE_HEADER_COLOR = (50, 50, 150, 255)


def get_resource_cached(url: str):
    name = "cache/" + url.split("/")[-1]
    try:
        open(name, "rb")

    except FileNotFoundError:
        content: Response = requests.get(url, stream=True)
        sleep(0.5)

        with open("cache/" + url.split("/")[-1], "wb") as f:
            for chunk in content.iter_content(1024):
                f.write(chunk)

    return Path(name).absolute()


def create_text_image(
    text: str,
    size: tuple[int, int] = (TITLE_CARD_WIDTH, TITLE_NAMEPLATE_HEIGHT),
    font_size: int = 50,
    align: Literal["left", "center", "right"] = "center",
    anchor: str = "mm",
    font: str = FONT_BASIC,
    fill_color: tuple[int, int, int, int] | str = "black",
    multiline = False,
):
    with Image.new("RGB", size, "white") as image:
        draw = ImageDraw.Draw(image)

        font = ImageFont.truetype(font, font_size)

        if multiline:
            content = ""
            words = text.split()
            for word in words:
                if font.getlength(content) + font.getlength(word) > AVATAR_H_SIZE - 5:
                    content += "\n"
                content += word + " "
        else:
            content = text


        draw_func = draw.multiline_text if multiline else draw.text
        draw_func((image.size[0] // 2, image.size[1] // 2), content, fill_color,
                  align=align, font=font, anchor=anchor,
                  )
        # image.show()
    return image


def merge_images(
    images: list[Image],
    direction: Literal["h", "v"] = "v",
    margins: tuple[int, int] = (MARGIN_HORIZONTAL, MARGIN_VERTICAL),
    border: tuple[int, int, int, int] | None = None,
):
    images = [image for image in images if image]

    if not images:
        return None

    if len(images) == 1:
        return images[0]

    h_margin, v_margin = margins

    if direction == "v":
        iterate_by = 1
        iterate_margin = v_margin
        wrap_margin = h_margin
    else:
        iterate_by = 0
        iterate_margin = h_margin
        wrap_margin = v_margin

    max_size = sum_size = 0
    for img in images:
        max_size = max(img.size[1 - iterate_by], max_size)
        sum_size += img.size[iterate_by]

    max_size += wrap_margin * 2
    sum_size += iterate_margin * (len(images) + 1)

    if direction == "v":
        size = (max_size, sum_size)
    else:
        size = (sum_size, max_size)

    collated = Image.new("RGB", size, color=BG_COLOR)
    iter_position = iterate_margin
    for img in images:
        if direction == "v":
            box = (max_size // 2 - img.size[1 - iterate_by] // 2 + wrap_margin, iter_position)
        else:
            box = (iter_position, wrap_margin)
        collated.paste(img, box=box)
        iter_position += img.size[iterate_by] + iterate_margin

    if border:
        draw = ImageDraw.Draw(collated)
        draw.rectangle((0, 0, collated.size[0] - 1, collated.size[1] - 1), outline=border, width=2)

    return collated


def make_char_cards_for_title(title_data: list[tuple[int, str, str]]):
    char_cards = []
    for img_data in title_data:
        char_id, char_name, img_url = img_data
        name_image = create_text_image(
            char_name, font=FONT_BASIC, anchor="mm", size=(AVATAR_H_SIZE, CHAR_NAMEPLATE_HEIGHT),
            font_size=FONT_CHAR_SIZE, fill_color=(0, 0, 0, 255), multiline=True,
        )
        img = Image.open(get_resource_cached(img_url))
        img = img.resize(
            (225, int(img.size[1] * CHAR_IMAGE_CUT_PART * 225 / img.size[0])),
            box=(0, 0, img.size[0], img.size[1] * CHAR_IMAGE_CUT_PART),
        )
        img.save(f"img/{char_id}.jpg")
        img = img.resize(
            (AVATAR_H_SIZE, int(img.size[1] * AVATAR_H_SIZE / img.size[0])),
            box=(0, 0, img.size[0], img.size[1]),
        )

        char_card = merge_images([img, name_image], "v")

        char_cards.append(char_card)

    return char_cards


class CharacterCard:
    def __init__(self, name: str, img_url: str, char_id: int):
        self.name = name
        self.img_url = img_url
        self.char_id = char_id
        self.text_image = None
        self.char_image = None
        self.card_image = None

    def _generate_name_image(self):
        self.text_image = create_text_image(
            self.name, font=FONT_BASIC, anchor="mm", size=(AVATAR_H_SIZE, CHAR_NAMEPLATE_HEIGHT),
            font_size=FONT_CHAR_SIZE, fill_color="black", multiline=True,
        )
        return self.text_image

    def _generate_char_image(self):
        img = Image.open(get_resource_cached(self.img_url))
        self.char_image = img.resize(
            (AVATAR_H_SIZE, int(img.size[1] * CHAR_IMAGE_CUT_PART * AVATAR_H_SIZE / img.size[0])),
            box=(0, 0, img.size[0], img.size[1] * CHAR_IMAGE_CUT_PART),
        )
        return self.char_image

    def make_card(self):
        name_image = self._generate_name_image()
        char_image = self._generate_char_image()
        self.card_image = merge_images([char_image, name_image], "v")
        return self.card_image


class TitleCard:
    def __init__(self, title: str, char_data: list[tuple[int, str, str]]):
        self.title = title
        self.title_width = self._get_title_width()
        self.char_data = char_data
        self.header_image = None
        self.title_image = None
        self.characters: list[CharacterCard] = []
        self.width_stackable: bool = False if self._get_width_in_cards() > 4 else True
        self.height_in_cards: int = math.ceil(len(self.char_data) / CARD_H_AMOUNT)
        print(self.title, self.title_width, self._get_width_in_cards(), self.width_stackable)

    def _get_title_width(self):
        font = ImageFont.truetype(FONT_BASIC, FONT_TITLE_SIZE)

        return round(font.getlength(self.title))

    def _get_width_in_cards(self):
        return max(len(self.char_data), math.ceil(self._get_title_width() / (AVATAR_H_SIZE + MARGIN_HORIZONTAL)))

    def _generate_header_image(self):
        # calculate title width via PIL text size
        self.header_image = create_text_image(self.title, font=FONT_BASIC, font_size=FONT_TITLE_SIZE, fill_color=TITLE_HEADER_COLOR)

        return self.header_image

    def make_card(self):
        for char_id, name, img_url in self.char_data:
            self.characters.append(CharacterCard(name, img_url, char_id))

        rows = []
        for i in range(0, len(character_cards), CARD_H_AMOUNT):
            char_cards_chunk = character_cards[i:i + CARD_H_AMOUNT]
            rows.append(merge_images(char_cards_chunk, "h", margins=(0, 0)))

        character_cards_image = merge_images(rows, "v", margins=(0, 0))

        self.title_image = merge_images([header_image, character_cards_image], "v", margins=(0, 0), border=(255, 255, 255, 255))

        return self.title_image


class VotingCard:
    def __init__(
        self,
        season_name: str,
        season_id: str,
        title_data: list[tuple[str, int, str, str]]
    ):
        self.season_name = season_name
        self.season_id = season_id
        self.title_data = title_data
        self.titles: list[TitleCard] = []
        self.prepare()

    def prepare(self):
        columns = [list() for _ in range(COLUMN_COUNT + 1)]
        max_width = 0
        total_height = 0

        titles = defaultdict(list)

        for t in self.title_data:
            titles[t[0]].append((t[1], t[2], t[3]))

        for title in titles.keys():
            self.titles.append(TitleCard(title, titles[title]))


        column_size = math.ceil(len(titles.keys()) / COLUMN_COUNT)


def make_collage(title_tuples: list[tuple[str, int, str, str]], season_name: str):
    logger.info(f"Making collage for {title_tuples}")
    columns = [list() for _ in range(COLUMN_COUNT + 1)]
    max_width = 0
    total_height = 0

    titles = defaultdict(list)

    for t in title_tuples:
        titles[t[0]].append((t[1], t[2], t[3]))

    data_dict = {
        "candidates": [
            {
                "name": title_tuple[2],
                "source": title_tuple[0],
                "selected": False,
                "img": f"/img/{title_tuple[1]}.jpg",
            } for title_tuple in title_tuples
        ],
        "title": season_name,
    }
    logger.debug("data_dict: %s", data_dict)

    with open("data.json", "w") as f:
        json.dump(data_dict, f)

    column_size = math.ceil(len(titles.keys()) / COLUMN_COUNT)

    title_cards = []
    for title in titles.keys():
        header_image = create_text_image(title, font=FONT_BASIC, font_size=FONT_TITLE_SIZE, fill_color=TITLE_HEADER_COLOR)

        character_cards = make_char_cards_for_title(titles[title])

        rows = []
        for i in range(0, len(character_cards), CARD_H_AMOUNT):
            char_cards_chunk = character_cards[i:i + CARD_H_AMOUNT]
            rows.append(merge_images(char_cards_chunk, "h", margins=(0, 0)))

        character_cards_image = merge_images(rows, "v", margins=(0, 0))

        title_card = merge_images([header_image, character_cards_image], "v", margins=(0, 0), border=(255, 255, 255, 255))
        title_cards.append(title_card)
        total_height += title_card.size[1]

    current_height = 0
    column_index = 0

    for tc in title_cards:
        columns[column_index].append(tc)
        current_height += tc.size[1]

        if current_height > total_height / COLUMN_COUNT:
            column_index += 1
            current_height = 0

    columns_images = [merge_images(column, "v") for column in columns]
    cards = merge_images(columns_images, "h", margins=(0, 0))

    voting_header = create_text_image(season_name, size=(cards.size[0], 80), font_size=FONT_HEADER_SIZE, font=FONT_HEADER,
                                      fill_color=VOTING_HEADER_COLOR, anchor="mm")
    collage = merge_images([voting_header, cards], "v")
    print(collage.size)

    # collage.show()
    byte_image = io.BytesIO()
    collage.save(byte_image, format="PNG")
    byte_image.seek(0)
    # collage.save("img/collage.png")
    return byte_image

