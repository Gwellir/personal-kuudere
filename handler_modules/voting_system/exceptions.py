class VotingCompletedError(Exception):
    pass


class CharIDNotFoundError(Exception):
    pass


class NoLegitAnimeError(Exception):
    pass


class AlreadyReleasedError(Exception):
    pass


class MalformedABParamsError(Exception):
    pass


class DuplicateVotingItemsError(Exception):
    pass


class VotingIsFinishedError(Exception):
    pass


class InvalidVotesError(Exception):
    pass

class NotAChatMember(Exception):
    pass
