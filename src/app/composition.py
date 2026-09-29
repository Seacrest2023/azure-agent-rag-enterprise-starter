"""The composition root: the one place the app is assembled from its parts.

Each external service (the models, Document Intelligence, AI Search, Blob Storage,
publishing events, the clock) reaches the code through a small interface held in
`Services`. Production passes the real adapters; tests pass fakes from tests/fakes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Services:
    """The external services the app uses. Each adapter adds a field here."""


@dataclass(frozen=True)
class App:
    """The assembled app. Each feature adds its entry point here."""

    services: Services


def build_app(services: Services) -> App:
    return App(services=services)
