"""Fakes for the external services: one per service, shared by every test."""

from app.composition import Services


def fake_services() -> Services:
    """The app's services, each replaced by its fake."""
    return Services()
