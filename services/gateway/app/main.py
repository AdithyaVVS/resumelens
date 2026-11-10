import asyncio
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.limiter import RateLimiter

_client = httpx.AsyncClient()
limiter = RateLimiter(limit=settings.auth_rate_limit)

PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
FORWARD_HEADERS = {"authorization", "content-type", "accept"}
# public name -> (which service, path prefix inside that service)
ROUTES = {
    "auth": ("auth", "/auth"),
    "resumes": ("resume", "/resumes"),
    "analysis": ("analysis", "/analysis"),
    "jobs": ("jobs", "/jobs"),
}


async def get_client() -> httpx.AsyncClient:
    return _client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await _client.aclose()


app = FastAPI(title="ResumeLens gateway", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=PROXY_METHODS + ["OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def service_urls() -> dict[str, str]:
    """The services that are switched on (their address is set)."""
    candidates = {
        "auth": settings.auth_url,
        "resume": settings.resume_url,
        "analysis": settings.analysis_url,
        "jobs": settings.jobs_url,
    }
    return {name: url.rstrip("/") for name, url in candidates.items() if url.strip()}


RETRY_DELAY = 2.0  # seconds between attempts while a service is waking up


async def check(
    client: httpx.AsyncClient, name: str, url: str, timeout: float, patience: float = 0.0
):
    """Asks a service for its health. With patience, keeps asking until it answers
    or the time runs out: a sleeping free-tier service answers 502 for about a minute."""
    deadline = time.monotonic() + patience
    while True:
        try:
            response = await client.get(f"{url}/health", timeout=timeout)
            if response.status_code == 200:
                return name, response.json()
            result = {"status": "error", "code": response.status_code}
        except Exception:
            result = {"status": "unreachable"}
        if time.monotonic() + RETRY_DELAY >= deadline:
            return name, result
        await asyncio.sleep(RETRY_DELAY)


async def check_all(client: httpx.AsyncClient, timeout: float, patience: float = 0.0) -> dict:
    results = await asyncio.gather(
        *(check(client, name, url, timeout, patience) for name, url in service_urls().items())
    )
    services = dict(results)
    all_ok = all(s.get("status") == "ok" for s in services.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "gateway": "ok",
        "services": services,
    }


@app.get("/api/health")
async def health(client: httpx.AsyncClient = Depends(get_client)):
    return await check_all(client, timeout=5)


@app.get("/api/warmup")
async def warmup(
    patience: float = Query(50, ge=0, le=50),
    client: httpx.AsyncClient = Depends(get_client),
):
    """Reports whether every service is up, waiting up to `patience` seconds.

    Free hosting wakes a sleeping service when a browser asks for it, but not when
    another service does. So every service that is not up comes with a wake_url, and
    the browser opens those addresses itself."""
    started = time.monotonic()
    result = await check_all(client, timeout=10, patience=patience)
    urls = service_urls()
    for name, info in result["services"].items():
        if info.get("status") != "ok":
            info["wake_url"] = f"{urls[name]}/health"
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


async def forward(
    request: Request, service: str, path: str, client: httpx.AsyncClient
) -> Response:
    route = ROUTES.get(service)
    if route is None or ".." in path.split("/"):
        raise HTTPException(status_code=404, detail="Not found")
    target, prefix = route
    urls = service_urls()
    if target not in urls:
        raise HTTPException(status_code=404, detail="Not found")

    if service == "auth" and request.method == "POST" and path in {"login", "register"}:
        caller = request.client.host if request.client else "unknown"
        if not limiter.allow(caller):
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please wait a minute and try again.",
            )

    body = await request.body()
    if len(body) > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="Request too large")

    url = urls[target] + prefix + (f"/{path}" if path else "")
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in FORWARD_HEADERS
    }
    timeout = 60.0 if target == "analysis" else 30.0
    try:
        upstream = await client.request(
            request.method,
            url,
            params=list(request.query_params.multi_items()),
            content=body,
            headers=headers,
            timeout=timeout,
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504, detail=f"The {target} service took too long to respond."
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail=f"The {target} service is unavailable. "
            "It may be waking up, so try again in a moment.",
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.api_route("/api/{service}", methods=PROXY_METHODS)
async def proxy_root(
    service: str, request: Request, client: httpx.AsyncClient = Depends(get_client)
):
    return await forward(request, service, "", client)


@app.api_route("/api/{service}/{path:path}", methods=PROXY_METHODS)
async def proxy_path(
    service: str,
    path: str,
    request: Request,
    client: httpx.AsyncClient = Depends(get_client),
):
    return await forward(request, service, path, client)
