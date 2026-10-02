"""Portfolio accounting exceptions."""

from __future__ import annotations


class PortfolioError(Exception):
    """Base class for portfolio accounting errors."""


class PortfolioProjectionError(PortfolioError):
    """Raised when a portfolio projection receives inconsistent inputs."""
