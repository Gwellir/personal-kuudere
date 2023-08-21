import abc
import dataclasses
import itertools
import math
import os
import random
import copy

import dill as pickle

from orm.ORMWrapper import VotedCharacters
from .exceptions import DuplicateVotingItemsError, VotingIsFinishedError, InvalidVotesError

from typing import TYPE_CHECKING, List, Dict

from ..base import HandlerError

if TYPE_CHECKING:
    from typing import Hashable


class Displayable(abc.ABC):
    """
    Abstract base with minimal required parameters for displaying an entry in a voting
    """
    @abc.abstractmethod
    def get_picture(self) -> str:
        """Returns picture path"""
        pass

    @abc.abstractmethod
    def get_name(self) -> str:
        """Returns a name or title for the entry"""
        pass

    @abc.abstractmethod
    def get_category(self) -> str:
        """Returns entry's type or category or secondary description"""
        pass


class DisplayableCharacter(Displayable):
    """
    A wrapper for representing an anime character in voting
    """

    def __init__(self, voted_character: VotedCharacters):
        self.voted_character = voted_character

    def __repr__(self):
        return f"{self.voted_character.name} ({self.voted_character.title}): {self.voted_character.image_url}"

    __str__ = __repr__

    def get_picture(self) -> str:
        return self.voted_character.image_url

    def get_name(self) -> str:
        return self.voted_character.name

    def get_category(self) -> str:
        return self.voted_character.title


@dataclasses.dataclass
class Position:
    """A class for describing a position in voting"""

    item: Displayable
    current_votes: int
    seed_number: int


class VotingSystem:
    bot_data_param = "current_voting"
    pickle_file = "voting.pickle"
    max_grid_size = 32

    def __init__(self, name: str, items: List[Displayable]):
        self.name = name
        self.items = items
        self.item_to_item_number = {item: i for i, item in enumerate(self.items)}
        if len(self.items) > len(set(items)):
            raise DuplicateVotingItemsError
        self.positions = [Position(item, 0, 0) for item in items]
        self.stage = 0
        self.grid_size = len(self.items)
        self.user_votes: Dict[Hashable, List[bool]] = dict()
        self.results: List[List[Position]] = []
        self.is_finished = False
        self.store()

    def get_stage_name(self):
        if self.stage == 0:
            return "Отборочный тур"
        elif self.grid_size == 8:
            return "Четвертьфинал"
        elif self.grid_size == 4:
            return "Полуфинал"
        elif self.grid_size == 2:
            return "Финал"
        elif self.grid_size == 1:
            return "Завершено"
        else:
            return f"1/{self.grid_size // 2} финала"

    @classmethod
    def get_voting(cls, bot_data):
        if not (vs := bot_data.get(cls.bot_data_param)):
            try:
                vs = cls._restore()
                bot_data[cls.bot_data_param] = vs
            except FileNotFoundError:
                raise HandlerError(f"Не ведётся никакое текущее голосование!")

        return vs

    @classmethod
    def clear(cls, bot_data):
        os.remove(cls.pickle_file)
        vs = bot_data.pop(cls.bot_data_param)
        return vs

    @classmethod
    def _restore(cls) -> "VotingSystem":
        with open(cls.pickle_file, "rb") as f:
            vs = pickle.load(f, ignore=True)
            return vs

    def store(self):
        with open(self.pickle_file, "wb") as f:
            pickle.dump(self, f)

    def get_all_results(self):
        return self.results

    def get_current_round_candidates(self):
        return [(pos.item, pos.seed_number) for pos in self.positions]

    def get_current_available_string(self):
        if self.stage > 0:
            return "".join([f"{self.item_to_item_number[pos.item]:02}" for pos in self.positions])

    def set_user_votes(self, user: "Hashable", vote_list: List[bool]):
        if self.is_finished:
            raise VotingIsFinishedError
        votes = self.user_votes.get(user)
        if votes:
            for i, vote in enumerate(votes):
                if vote:
                    self.positions[i].current_votes -= 1
        if self.stage > 0:
            self._validate_votes(vote_list, votes)

        for i, vote in enumerate(vote_list):
            if vote:
                self.positions[i].current_votes += 1
        self.user_votes[user] = vote_list
        print([f"{pos.current_votes} {pos.seed_number}" for pos in self.positions])
        self.store()

    def _validate_votes(self, vote_list, prev_votes):
        for i in range(self.grid_size // 2):
            if prev_votes and prev_votes[2 * i:2 * i + 2] != [False, False]:
                if vote_list[2*i:2*i + 2] != prev_votes[2 * i:2 * i + 2]:
                    raise InvalidVotesError
            if vote_list[2*i] and vote_list[2*i + 1]:
                # Cannot vote for both candidates in a pair
                raise InvalidVotesError

    def advance_stage(self):
        if self.is_finished:
            raise VotingIsFinishedError
        print([f"{pos.current_votes} {pos.seed_number}" for pos in self.positions])
        if self.stage == 0:
            self._build_seeded_bracket()
        else:
            self.results.append(copy.deepcopy(self.positions))
            self._remove_losers()
            self.grid_size //= 2
        # set current votes for round to 0
        for pos in self.positions:
            pos.current_votes = 0
        self.stage += 1
        self.user_votes = {}
        if self.grid_size == 1:
            print(self.positions)
            self.is_finished = True
        self.store()

    def _build_seeded_bracket(self):
        random.shuffle(self.positions)
        self.positions = sorted(self.positions, key=lambda item: item.current_votes, reverse=True)
        self.results.append(copy.deepcopy(self.positions))

        self.grid_size = self.get_bracket_size()
        self.positions = self.positions[:self.grid_size]
        for seed, position in enumerate(self.positions):
            position.seed_number = seed + 1

        pairings = self._build_pairs(self.grid_size)
        self.positions = [self.positions[i] for i in pairings]
        self.store()

    def get_bracket_size(self):
        bracket_rounds = int(math.log2(len(self.items)))
        return min(2 ** bracket_rounds, self.max_grid_size)

    def _remove_losers(self):
        winner_list = [False for _ in self.positions]
        for i in range(self.grid_size // 2):
            if self.positions[2*i].current_votes > self.positions[2*i + 1].current_votes:
                winner_list[2*i] = True
            elif (
                self.positions[2*i].current_votes == self.positions[2*i + 1].current_votes
                and self.positions[2*i].seed_number < self.positions[2*i + 1].seed_number
            ):
                winner_list[2*i] = True
            else:
                winner_list[2*i + 1] = True
        print(winner_list)
        self.positions = list(itertools.compress(self.positions, winner_list))
        self.store()

    @staticmethod
    def _build_pairs(bracket_size: int):
        nums = [0, ]
        i = 0
        while bracket_size > len(nums):
            i += 1
            top = 2 ** i - 1
            nums_add = [top - n for n in nums]
            nums = list(itertools.chain(*zip(nums, nums_add)))
        return nums
