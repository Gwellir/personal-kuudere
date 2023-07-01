import random
import pytest
import pprint

from orm.ORMWrapper import BaseRelations, VotedCharacters, SeasonalVotings

from .system import VotingSystem, DisplayableCharacter


@pytest.fixture
def session():
    br = BaseRelations()
    return br.get_session()


@pytest.fixture
def voted_characters(session):
    return (
        session.query(VotedCharacters)
        .join(SeasonalVotings)
        .filter(SeasonalVotings.id == 1)
    )


@pytest.fixture
def voting_system(voted_characters) -> VotingSystem:
    item_list = [DisplayableCharacter(char) for char in voted_characters]
    return VotingSystem("test", item_list)


@pytest.fixture
def random_vote_set_with_checksum():
    def inner():
        votes = dict()
        sum_list = [0 for _ in range(100)]
        for i in range(random.randint(10, 20)):
            user_votes = [bool(random.randint(0, 1)) for _ in range(100)]
            votes[f"test_user_{i}"] = user_votes
            for j in range(100):
                sum_list[j] += int(user_votes[j])

        return votes, sum_list

    return inner


@pytest.fixture
def random_round_vote_set_with_checksum():
    def inner():
        votes = dict()
        sum_list = [0 for _ in range(100)]
        for i in range(random.randint(10, 20)):
            user_votes = []
            for _ in range(50):
                num = random.randint(0, 2)
                if num == 0:
                    user_votes.extend([False, False])
                elif num == 1:
                    user_votes.extend([False, True])
                else:
                    user_votes.extend([True, False])
            votes[f"test_user_{i}"] = user_votes
            for j in range(100):
                sum_list[j] += int(user_votes[j])

        return votes, sum_list

    return inner


class TestVotingSystem:

    def test_base_state(self, voting_system):
        assert len(voting_system.positions) == 46
        candidates = voting_system.get_current_round_candidates()
        assert len(candidates) == 46
        assert candidates[0][0].voted_character.name == "Flan"
        assert candidates[0][0].voted_character.title == "Majo no Tabitabi"
        assert candidates[0][1] == 0
        assert voting_system.stage == 0
        assert voting_system.get_all_results() == []

    def test_user_votes(self, voting_system, random_vote_set_with_checksum):
        size = voting_system.grid_size
        votes_dict, checksum = random_vote_set_with_checksum()
        for user in votes_dict:
            voting_system.set_user_votes(user, votes_dict[user][:size])
        assert "test_user_9" in voting_system.user_votes
        assert len(voting_system.user_votes) == len(votes_dict)
        assert [pos.current_votes for pos in voting_system.positions] == checksum[:size]

    def test_seeding(self, voting_system, random_vote_set_with_checksum, capsys):
        size = voting_system.grid_size
        votes_dict, checksum = random_vote_set_with_checksum()
        for user in votes_dict:
            voting_system.set_user_votes(user, votes_dict[user][:size])
        voting_system.advance_stage()
        assert voting_system.stage == 1
        assert voting_system.grid_size == len(voting_system.positions) == 32
        assert len(voting_system.get_all_results()[0]) == 46
        # pprint.pprint(voting_system.get_all_results()[0])
        set1 = set([res.item.voted_character.name for res in voting_system.get_all_results()[0] if res.seed_number > 0])
        set2 = set([pos.item.voted_character.name for pos in voting_system.positions])
        assert set1 == set2

    def test_voting(self, voting_system, random_vote_set_with_checksum, random_round_vote_set_with_checksum, capsys):
        size = voting_system.grid_size
        votes_dict, checksum = random_vote_set_with_checksum()
        for user in votes_dict:
            voting_system.set_user_votes(user, votes_dict[user][:size])
        voting_system.advance_stage()
        while not voting_system.is_finished:
            size = voting_system.grid_size
            # print(size, type(size))
            # print(len(voting_system.positions))
            votes_dict, checksum = random_round_vote_set_with_checksum()
            for user in votes_dict:
                voting_system.set_user_votes(user, votes_dict[user][:size])
            voting_system.advance_stage()

