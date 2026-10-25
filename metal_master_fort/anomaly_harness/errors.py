"""Errors the anomaly harness raises on purpose."""


class HarnessError(Exception):
    """A local config, sample, or baseline problem.

    This is a data error for the medic to triage. It is not a metric strike.
    """
