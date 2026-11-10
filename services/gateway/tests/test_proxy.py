import json

import httpx
import pytest

from app.config import settings


def test_forwards_request_and_query_string(client, upstream):
    response = client.get("/api/resumes?limit=5")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert str(upstream.requests[0].url) == "http://resume:8000/resumes?limit=5"


@pytest.mark.parametrize(
    "method, path, expected",
    [
        ("POST", "/api/auth/login", "http://auth:8000/auth/login"),
        ("GET", "/api/auth/me", "http://auth:8000/auth/me"),
        ("GET", "/api/resumes/5/versions/2", "http://resume:8000/resumes/5/versions/2"),
        ("PUT", "/api/resumes/5", "http://resume:8000/resumes/5"),
        ("POST", "/api/analysis/run", "http://analysis:8000/analysis/run"),
        ("GET", "/api/jobs", "http://jobs:8000/jobs"),
    ],
)
def test_routes_to_the_right_service(client, upstream, method, path, expected):
    client.request(method, path, json={} if method != "GET" else None)
    assert str(upstream.requests[0].url) == expected


def test_forwards_token_and_body_but_not_other_headers(client, upstream):
    client.post(
        "/api/analysis/run",
        json={"job": "hello"},
        headers={"Authorization": "Bearer abc", "X-Secret": "nope"},
    )
    seen = upstream.requests[0]
    assert seen.headers["authorization"] == "Bearer abc"
    assert "x-secret" not in seen.headers
    assert json.loads(seen.content) == {"job": "hello"}


def test_passes_through_upstream_errors(client, upstream):
    upstream.respond = lambda request: httpx.Response(404, json={"detail": "Resume not found"})
    response = client.get("/api/resumes/99")
    assert response.status_code == 404
    assert response.json() == {"detail": "Resume not found"}


def test_passes_through_empty_204(client, upstream):
    upstream.respond = lambda request: httpx.Response(204)
    response = client.delete("/api/resumes/1")
    assert response.status_code == 204
    assert response.content == b""


def test_unknown_service_is_404_and_not_forwarded(client, upstream):
    assert client.get("/api/secret/anything").status_code == 404
    assert upstream.requests == []


def test_a_service_that_is_switched_off_is_404(client, upstream, monkeypatch):
    monkeypatch.setattr(settings, "jobs_url", "")
    assert client.get("/api/jobs").status_code == 404
    assert upstream.requests == []


def test_path_traversal_is_rejected(client, upstream):
    assert client.get("/api/resumes/%2e%2e/%2e%2e/health").status_code == 404
    assert upstream.requests == []


def test_unreachable_service_returns_503(client, upstream):
    def refuse(request):
        raise httpx.ConnectError("refused")

    upstream.respond = refuse
    response = client.get("/api/resumes")
    assert response.status_code == 503
    assert "resume" in response.json()["detail"]


def test_slow_service_returns_504(client, upstream):
    def too_slow(request):
        raise httpx.ReadTimeout("slow")

    upstream.respond = too_slow
    assert client.get("/api/analysis/status").status_code == 504


def test_oversized_body_is_rejected(client, upstream):
    response = client.post("/api/analysis/run", content=b"x" * 70000)
    assert response.status_code == 413
    assert upstream.requests == []
