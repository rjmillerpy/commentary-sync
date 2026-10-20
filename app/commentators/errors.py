"""Errors the commentators domain reports to its callers."""


class CommentatorsError(Exception):
    """Base class: anything the commentators domain can fail with."""


class AlreadyCommentatorError(CommentatorsError):
    """This account already has a commentator profile."""


class HandleTakenError(CommentatorsError):
    """Another commentator uses this handle."""


class NotACommentatorError(CommentatorsError):
    """The signed-in account has no commentator profile."""


class CommentatorNotFoundError(CommentatorsError):
    """No commentator has the requested handle."""
