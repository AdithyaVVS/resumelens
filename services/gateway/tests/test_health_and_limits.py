import httpx

import app.main as gateway
from app.config import settings


def service_health(request):
    name = request.url.host
    return httpx.Response(200, json={"status": "ok", "service": name})


def test_health_reports_every_service_that_is_switched_on(client, upstream):
    upstream.respond = service_health
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert set(body["services"]) == {"auth", "resume", "analysis", "jobs"}


def test_health_skips_services_that_are_switched_off(client, upstream, monkeypatch):
    monkeypatch.setattr(settings, "resume_url", "")
    monkeypatch.setattr(settings, "analysis_url", "")
    monkeypatch.setattr(settings, "jobs_url", "")
    upstream.respond = service_health
    body = client.get("/api/health").json()
    assert set(body["services"]) == {"auth"}


def test_health_reports_degraded_when_one_is_down(client, upstream):
    def respond(request):
        if request.url.host == "resume":
            raise httpx.ConnectError("down")
        return service_health(request)

    upstream.respond = respond
    body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["services"]["resume"] == {"status": "unreachable"}
    assert body["services"]["auth"]["status"] == "ok"


def test_warmup_wakes_all_services_and_reports_time(client, upstream):
    upstream.respond = service_health
    body = client.get("/api/warmup").json()
    assert body["status"] == "ok"
    assert isinstance(body["elapsed_ms"], int)
    assert sorted(r.url.host for r in upstream.requests) == ["analysis", "auth", "jobs", "resume"]


def test_login_and_register_are_rate_limited(client, upstream):
    for _ in range(10):
        assert client.post("/api/auth/login", json={}).status_code == 200
    blocked = client.post("/api/auth/login", json={})
    assert blocked.status_code == 429
    assert client.post("/api/auth/register", json={}).status_code == 429
    assert len(upstream.requests) == 10
    # other endpoints are not affected
    assert client.get("/api/resumes").status_code == 200


def test_cors_allows_the_frontend_origin(client):
    response = client.options(
        "/api/resumes",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_blocks_other_origins(client):
    response = client.options(
        "/api/resumes",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_warmup_keeps_asking_while_a_service_wakes_up(client, upstream, monkeypatch):
    monkeypatch.setattr(gateway, "RETRY_DELAY", 0.0)
    attempts = {"resume": 0}

    def respond(request):
        if request.url.host == "resume":
            attempts["resume"] += 1
            if attempts["resume"] < 4:
                return httpx.Response(502)
        return service_health(request)

    upstream.respond = respond
    body = client.get("/api/warmup").json()
    assert body["status"] == "ok"
    assert attempts["resume"] == 4


def test_health_does_not_wait_for_a_sleeping_service(client, upstream):
    upstream.respond = lambda request: httpx.Response(502)
    body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["services"]["auth"] == {"status": "error", "code": 502}
    assert len(upstream.requests) == 4


def test_warmup_gives_the_browser_a_wake_url_for_services_that_are_down(client, upstream):
    def respond(request):
        if request.url.host == "resume":
            return httpx.Response(502)
        return service_health(request)

    upstream.respond = respond
    body = client.get("/api/warmup?patience=0").json()
    assert body["services"]["resume"]["wake_url"] == "http://resume:8000/health"
    assert "wake_url" not in body["services"]["auth"]
    assert sum(1 for r in upstream.requests if r.url.host == "resume") == 1


def test_warmup_rejects_an_absurd_patience(client):
    assert client.get("/api/warmup?patience=9999").status_code == 422
