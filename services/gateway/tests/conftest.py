import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, get_client, limiter


class Upstream:
    """Stands in for the other services: records requests, answers as scripted."""

    def __init__(self):
        self.requests = []
        self.respond = lambda request: httpx.Response(200, json={"ok": True})

    def __call__(self, request):
        self.requests.append(request)
        return self.respond(request)


@pytest.fixture
def upstream():
    return Upstream()


@pytest.fixture(autouse=True)
def all_services_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_url", "http://auth:8000")
    monkeypatch.setattr(settings, "resume_url", "http://resume:8000")
    monkeypatch.setattr(settings, "analysis_url", "http://analysis:8000")
    monkeypatch.setattr(settings, "jobs_url", "http://jobs:8000")


@pytest.fixture
def client(upstream):
    fake = httpx.AsyncClient(transport=httpx.MockTransport(upstream))

    async def override_get_client():
        return fake

    app.dependency_overrides[get_client] = override_get_client
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
