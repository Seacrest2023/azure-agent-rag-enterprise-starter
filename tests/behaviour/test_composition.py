from app.composition import App, build_app
from tests.fakes import fake_services


def test_app_is_assembled_from_the_services_it_is_given() -> None:
    services = fake_services()

    app = build_app(services)

    assert isinstance(app, App)
    assert app.services is services
