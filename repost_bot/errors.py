class DuplicateEventIgnored(Exception):
    """Raised when an already-processed source post is received again."""


class ValidationError(Exception):
    """Raised when inbound or outbound content is invalid."""


class TransientPublishError(Exception):
    """Raised when a publish attempt should be retried."""


class PermanentPublishError(Exception):
    """Raised when retrying a publish attempt is not useful."""


class UnauthorizedOperatorError(Exception):
    """Raised when an operator lacks permission for an admin action."""

