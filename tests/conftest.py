import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db"), "KITCHEN_PASSWORD": "secret-pass"})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def post(client):
    """POST a form with a valid CSRF token, the way the browser would."""

    def _post(url, data=None, **kwargs):
        client.get("/")  # make sure the session has a token
        with client.session_transaction() as s:
            token = s["csrf"]
        return client.post(url, data={"csrf": token, **(data or {})}, **kwargs)

    return _post
