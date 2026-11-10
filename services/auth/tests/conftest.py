import os

# These must be set before the app is imported, so the tests use the test database.
os.environ["JWT_SECRET"] = "test-secret-for-tests-only-0123456789abcdef"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://resumelens:resumelens@db:5432/resumelens_auth_test",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_tables():
    # Safety: never wipe a database that is not a test database.
    assert engine.url.database.endswith("_test"), "tests must use a *_test database"
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
