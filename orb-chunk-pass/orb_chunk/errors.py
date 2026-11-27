"""Errors for queue validation and planning."""


class QueueError(Exception):
    """One or more validation or planning errors. Exit code 2."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))
