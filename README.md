# ResumeLens

Tailor your resume to a job without lying. Work in progress.

Services: gateway, auth, resume, analysis, jobs (resume, analysis and jobs are added step by step).

Run locally (Docker Desktop required):

```
copy .env.example .env      (then set JWT_SECRET to a long random value)
docker compose up --build -d
node scripts/smoke.mjs
```

Ports: gateway 9000, auth 9001, database 5435 (chosen so it can run next to NotePilot).
