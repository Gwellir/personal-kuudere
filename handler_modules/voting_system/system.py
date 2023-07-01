import abc
import dataclasses
import itertools
import math

from orm.ORMWrapper import VotedCharacters
from .exceptions import DuplicateVotingItemsError, VotingIsFinishedError, InvalidVotesError

from typing import TYPE_CHECKING, List, Dict
if TYPE_CHECKING:
    from typing import Any


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

    def __init__(self, name: str, items: List[Displayable]):
        self.name = name
        self.items = items
        if len(self.items) > len(set(items)):
            raise DuplicateVotingItemsError
        self.positions = [Position(item, 0, 0) for item in items]
        self.stage = 0
        self.grid_size = len(self.items)
        self.user_votes: Dict[Any, List[bool]] = dict()
        self.results: List[List[Position]] = []
        self.is_finished = False

    def get_all_results(self):
        return self.results

    def get_current_round_candidates(self):
        return [(pos.item, pos.seed_number) for pos in self.positions]

    def set_user_votes(self, user: "Any", vote_list: List[bool]):
        if self.is_finished:
            raise VotingIsFinishedError
        if user in self.user_votes:
            votes = self.user_votes.get(user)
            for i, vote in enumerate(votes):
                if vote:
                    self.positions[i].current_votes -= 1
        if self.stage > 0:
            self._validate_votes(vote_list)
        for i, vote in enumerate(vote_list):
            if vote:
                self.positions[i].current_votes += 1
        self.user_votes[user] = vote_list

    def _validate_votes(self, vote_list):
        for i in range(self.grid_size // 2):
            if vote_list[2*i] and vote_list[2*i + 1]:
                # Cannot vote for both candidates in a pair
                raise InvalidVotesError

    def advance_stage(self):
        if self.is_finished:
            raise VotingIsFinishedError
        self.results.append(self.positions.copy())
        if self.stage == 0:
            self._build_seeded_grid()
        else:
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

    def _build_seeded_grid(self):
        self.positions = sorted(self.positions, key=lambda item: item.current_votes, reverse=True)
        grid_rounds = int(math.log2(len(self.positions)))
        self.grid_size = 2 ** grid_rounds
        self.positions = self.positions[:self.grid_size]
        for seed, position in enumerate(self.positions):
            position.seed_number = seed + 1

        pairings = self._build_pairs(grid_rounds)
        self.positions = [self.positions[i] for i in pairings]

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
        print([f"{pos.current_votes} {pos.seed_number}" for pos in self.positions])
        print(winner_list)
        self.positions = list(itertools.compress(self.positions, winner_list))

    @staticmethod
    def _build_pairs(pwr2: int):
        nums = [0, ]
        i = 0
        while pwr2 > 0:
            i += 1
            top = 2 ** i - 1
            nums_add = [top - n for n in nums]
            nums = list(itertools.chain(*zip(nums, nums_add)))
            pwr2 -= 1
        return nums
