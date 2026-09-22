"""Risk engine exceptions."""

from __future__ import annotations


class RiskError(Exception):
    """Base class for risk engine errors."""


class RiskConfigurationError(RiskError):
    """Raised when a risk rule or context configuration is invalid."""


class RiskInputError(RiskError):
    """Raised when a risk rule receives invalid runtime inputs."""
