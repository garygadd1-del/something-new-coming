"""Errors raised by the Kalwi Ewok scaffold."""


class EwokError(Exception):
    """Base error. The launcher prints this and exits nonzero."""


class ConfigError(EwokError):
    """A role file or schema check failed."""


class ParseError(ConfigError):
    """A role or compose document used syntax this scaffold does not accept."""


class PlanError(EwokError):
    """A run plan violated an isolation gate."""
