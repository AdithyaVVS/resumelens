// End-to-end check through the gateway, the way the browser uses it.
// Usage:  node scripts/smoke.mjs [API_URL] [ALLOWED_ORIGIN]
// Defaults: http://127.0.0.1:9000/api  and  http://localhost:5173
const API = (process.argv[2] || "http://127.0.0.1:9000/api").replace(/\/+$/, "");
const ORIGIN = process.argv[3] || "http://localhost:5173";

let passed = 0;
let failed = 0;

function check(name, ok, detail = "") {
  if (ok) {
    passed += 1;
    console.log(`  PASS  ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL  ${name}${detail ? "  -> " + detail : ""}`);
  }
}

async function call(path, { method = "GET", body, token, headers = {} } = {}) {
  const h = { ...headers };
  if (body !== undefined) h["Content-Type"] = "application/json";
  if (token) h.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API}${path}`, {
    method,
    headers: h,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* 204 or no body */
  }
  return { status: response.status, data, headers: response.headers };
}

async function main() {
  const stamp = Date.now();
  const password = "smoke-test-pass-1";
  const email = `smoke-${stamp}@example.com`;

  console.log(`Testing ${API}\n`);

  console.log("Gateway");
  const health = await call("/health");
  check("health answers 200", health.status === 200, `got ${health.status}`);
  check("auth is reported ok", health.data?.services?.auth?.status === "ok", JSON.stringify(health.data));
  const unknown = await call("/nothing-here");
  check("an unknown route is 404", unknown.status === 404, `got ${unknown.status}`);

  console.log("\nAccounts");
  const reg = await call("/auth/register", { method: "POST", body: { email, password } });
  check("register returns 201", reg.status === 201, `got ${reg.status} ${JSON.stringify(reg.data)}`);
  const dup = await call("/auth/register", { method: "POST", body: { email, password } });
  check("registering the same email again returns 409", dup.status === 409, `got ${dup.status}`);
  const bad = await call("/auth/login", { method: "POST", body: { email, password: "wrong-password-1" } });
  check("wrong password is rejected (401)", bad.status === 401, `got ${bad.status}`);
  const login = await call("/auth/login", { method: "POST", body: { email, password } });
  check("login returns a token", login.status === 200 && !!login.data?.access_token, `got ${login.status}`);
  const token = login.data?.access_token;
  const me = await call("/auth/me", { token });
  check("/auth/me returns the email", me.data?.email === email, JSON.stringify(me.data));
  const anon = await call("/auth/me");
  check("/auth/me without a token is rejected (401)", anon.status === 401, `got ${anon.status}`);

  console.log("\nBrowser access (CORS)");
  const allowed = await call("/auth/me", {
    method: "OPTIONS",
    headers: {
      Origin: ORIGIN,
      "Access-Control-Request-Method": "GET",
      "Access-Control-Request-Headers": "authorization",
    },
  });
  check(
    `${ORIGIN} is allowed`,
    allowed.headers.get("access-control-allow-origin") === ORIGIN,
    `header was: ${allowed.headers.get("access-control-allow-origin")}`,
  );
  const stranger = await call("/auth/me", {
    method: "OPTIONS",
    headers: {
      Origin: "https://evil.example",
      "Access-Control-Request-Method": "GET",
      "Access-Control-Request-Headers": "authorization",
    },
  });
  check(
    "a stranger's website is not allowed",
    !stranger.headers.get("access-control-allow-origin"),
    `header was: ${stranger.headers.get("access-control-allow-origin")}`,
  );

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((problem) => {
  console.log(`\nCould not finish: ${problem.message}`);
  console.log("Is the backend running? Try:  docker compose ps");
  process.exit(1);
});
