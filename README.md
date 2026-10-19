# Pulse — Campaign & Notification Manager

A local, full-stack demo: manage contacts, create email campaigns, send them now or schedule them, and watch simulated deliveries progress in real time. It runs entirely on your machine with Docker. **No real email is ever sent**: delivery outcomes are simulated and repeatable.

```
pulse/                      monorepo
├── apps/api/               Python backend: one image, four entrypoints (api, worker, cron, init)
│   ├── app/api/            FastAPI routes and schemas (HTTP only)
│   ├── app/services/       business logic: dispatch, outbox relay, delivery processing, read models
│   ├── app/queue/          NATS JetStream helpers
│   ├── app/worker/         `python -m app.worker`
│   ├── app/tasks/          `python -m app.tasks.dispatch_due` (cron one-shot)
│   ├── app/seed/           idempotent demo seed
│   ├── alembic/            migrations
│   └── tests/              focused tests against real PostgreSQL
├── apps/web/               React + TypeScript + Vite + Tailwind + shadcn/ui + Recharts
├── scripts/reset-demo.sh   destructive demo reset (asks first)
├── Dockerfile              backend image (builds apps/api from the repo root)
├── package.json            root `npm run build` → builds apps/web into ./dist (static hosting)
├── docker-compose.yml
└── .env.example
```

## Start and stop

Requires Docker with Compose v2 (Apple Silicon and x86 both work).

```bash
docker compose up --build
```

The first build downloads images and dependencies. After that, normal operation needs no internet access.

Stop with `Ctrl+C`, or run `docker compose down` from another terminal. Data is kept in named volumes. `docker compose down -v` also deletes the volumes, and with them all data.

Configuration is read from `.env` (`cp .env.example .env`); see [Environment variables](#environment-variables).

## Local URLs

| What | URL |
|---|---|
| App | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| Liveness / readiness | http://localhost:8000/api/health · http://localhost:8000/api/ready |

Both are bound to `127.0.0.1`. PostgreSQL and NATS are not published to the host. To debug, use `docker compose exec postgres psql -U pulse`. The browser only talks to `localhost:3000`, and Vite proxies `/api` to the API container, so Docker service names never reach the browser.

## Architecture

```
 Browser ──▶ frontend (Vite, :3000) ──/api──▶ api (FastAPI, :8000) ──▶ PostgreSQL
                                                   │  Send Now / Retry: publish outbox rows immediately
                                                   ▼
 cron (Supercronic, every minute) ──▶ dispatch_due ──▶ NATS JetStream (durable work-queue stream)
                                                                     │ pull consumer, explicit ack
                                                                     ▼
                                                            worker (continuous) ──▶ PostgreSQL
```

| Service | Responsibility |
|---|---|
| `postgres` | System of record: contacts, campaigns, recipients, delivery runs/jobs/attempts, activity, outbox, worker heartbeats, cron runs. |
| `nats` | JetStream with file storage. Stream `PULSE_DELIVERIES` (work-queue retention, 2-minute duplicate window) and durable consumer `delivery-worker`. |
| `init` | Waits for dependencies, runs Alembic migrations, ensures the stream and consumer exist, seeds demo data once, then exits. Every other app service waits for it. |
| `api` | HTTP API. Validates input, runs the business logic, and publishes Send Now and retry jobs right away (best effort). |
| `worker` | Consumes job messages, simulates delivery, persists outcomes, schedules retries. Writes a heartbeat every 5 seconds. |
| `cron` | Supercronic runs the one-shot dispatcher every minute. It is not a Python scheduling loop. |
| `frontend` | Vite dev server with hot reload. |

### How delivery works

1. **Dispatch** (shared by Send Now, cron, and Retry Failed: `app/services/dispatch.py`). In one transaction it snapshots the subscribed contacts in the audience into `campaign_recipients`, creates a `delivery_run`, one `delivery_job` per recipient, and one `outbox` row per job. An empty audience completes immediately with "No eligible recipients".
2. **Outbox relay** (`app/services/outbox.py`). Pending rows are claimed with a short lease (`FOR UPDATE SKIP LOCKED`), published with `Nats-Msg-Id = job-<id>`, and marked published only after JetStream acknowledges. If a crash happens after publish but before marking, the row is republished once the lease expires. JetStream dedupes by message ID, and the worker is idempotent anyway.
3. **Worker** (`app/services/delivery.py`). The message only names a job; the job row is the source of truth. The worker claims the job with a row lock and a 30-second lease, rechecks that the contact is still subscribed (if not, the recipient is marked **skipped**), records the attempt (unique per job and attempt number), simulates for 0.6–1.0 seconds, and commits the outcome. It acks only after the commit. Messages for jobs that are already finished are simply acked, so duplicates never change counts.
4. **Retries.** Up to 3 attempts per run, waiting 5 seconds before attempt 2 and 20 seconds before attempt 3. The retry time is saved on the job, and the message is NAKed with that delay so JetStream redelivers it later. No worker sits sleeping.
5. **Completion.** When the last job of a run reaches a final state, the run closes and the campaign completes. Concurrent finishers serialize on the run row, so completion happens exactly once. Delivered, failed, and skipped all count as finished.
6. **Retry Failed** starts a new bounded run that covers only the failed recipients. Earlier attempts are kept. A partial unique index allows only one active run per campaign, so repeated clicks get a 409.

**Simulation** (`app/services/simulation.py`) is deterministic. About 3% of addresses always hard-bounce (keyed on the email). Every other recipient hashes `(campaign, contact)` into one of four profiles: delivered first time (84%), delivered after one or two transient failures, or delivered only after a manual retry (4%). Error messages look like real SMTP errors and are marked "(simulated)".

## How cron works

`apps/api/crontab` runs `python -m app.tasks.dispatch_due` every minute under [Supercronic](https://github.com/aptible/supercronic). Each invocation:

1. records a `cron_runs` row (start time),
2. claims due scheduled campaigns one at a time (`scheduled_at <= now`, `FOR UPDATE SKIP LOCKED`) and dispatches each in its own transaction,
3. publishes pending outbox rows to NATS, including rows left behind by a failed Send Now publish,
4. records finish time, result, counts and any error, then exits. The exit code is `1` on operational failure (for example, NATS unavailable) and `2` if the database can't be reached.

It is bounded (`CRON_CAMPAIGN_BATCH`, `CRON_OUTBOX_BATCH`, `CRON_MAX_SECONDS`) and safe to run repeatedly or concurrently. Cancelling locks the same campaign row and only succeeds while the campaign is still `scheduled`, so cancel and dispatch can't both win. Campaigns missed while the stack was down are dispatched on the next successful run. Scheduling is per minute, so a campaign starts within about a minute of its scheduled time. Times are stored in UTC and shown in **WIB (Asia/Jakarta, UTC+7)**.

The Job Activity page shows the last run, the last successful run, and the last result from `cron_runs`. Cron is a one-shot task, never shown as an "online" service. Worker status comes from heartbeats.

### Run cron manually

```bash
docker compose run --rm cron python -m app.tasks.dispatch_due
```

This replaces the cron service's normal Supercronic command for that one container (`make cron` does the same).

## Environment variables

All configuration lives in `.env` (git-ignored). Start from the template:

```bash
cp .env.example .env
```

Every variable has a working default, so `docker compose up` also works without a `.env`. Compose passes these values to the containers; nothing is hard-coded in the services.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://pulse:pulse@postgres:5432/pulse` | Database connection string for api, worker, cron and init. Plain `postgres://` / `postgresql://` URLs are accepted and use the psycopg driver |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `pulse` | Credentials for the bundled PostgreSQL container (keep in sync with `DATABASE_URL`) |
| `NATS_URL` | `nats://nats:4222` | Queue connection |
| `NATS_USER`, `NATS_PASSWORD` | empty | Queue credentials, used when they aren't embedded in `NATS_URL` |
| `PORT` | `8000` | API listen port for `python -m app.cli serve` (the image's default command) |
| `NATS_STREAM`, `NATS_SUBJECT`, `NATS_CONSUMER` | `PULSE_DELIVERIES`, `pulse.deliveries.email`, `delivery-worker` | JetStream names |
| `NATS_CONNECT_TIMEOUT_SECONDS` | `3` | Fail-fast timeout for queue connections |
| `VITE_API_BASE_URL` | `/api` | API base URL used by the browser. `/api` goes through the web proxy; an absolute URL such as `http://localhost:8000/api` calls the API directly |
| `API_PROXY_TARGET` | `http://api:8000` | Where the web dev server forwards `/api` (inside Docker) |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Origins allowed to call the API directly |
| `FRONTEND_PORT`, `API_PORT` | `3000`, `8000` | Host ports (bound to 127.0.0.1) |
| `LOG_LEVEL` | `INFO` | Structured JSON logs (no secrets or connection strings) |
| `DISPLAY_TIMEZONE` | `Asia/Jakarta` | Business day for "today" metrics and charts |
| `WORKER_CONCURRENCY` | `2` | Parallel deliveries per worker |
| `WORKER_HEARTBEAT_SECONDS`, `JOB_LEASE_SECONDS` | `5`, `30` | Heartbeat interval; how long a claimed job is reserved |
| `SIM_DELAY_MIN_MS`, `SIM_DELAY_MAX_MS` | `600`, `1000` | Simulated send time. Defaults process ~100 recipients in ~40 s |
| `DELIVERY_MAX_ATTEMPTS` | `3` | Attempts per delivery run |
| `RETRY_DELAYS_SECONDS` | `5,20` | Delay before attempt 2, 3, … |
| `CRON_CAMPAIGN_BATCH`, `CRON_OUTBOX_BATCH`, `CRON_MAX_SECONDS` | `20`, `500`, `45` | Per-invocation bounds |
| `OUTBOX_LEASE_SECONDS` | `30` | How long a claimed outbox row is reserved before republishing |
| `DEMO_SCHEDULE_OFFSET_MINUTES` | `5` | When the seeded scheduled campaign is due after first setup |

After changing `.env`, apply it with `docker compose up -d` (Compose recreates the affected containers).

## Deploying to NEO App

NEO App builds each service from the GitHub repo root, so the root is buildable: `Dockerfile` builds the backend image (every role; only the command differs), and the root `package.json` builds the web app into `dist/`. The image's default command, `python -m app.cli serve`, runs migrations and the one-time seed, then starts the API on `$PORT`.

| Pulse service | NEO App resource | Build from GitHub (repo root) | Command / settings |
|---|---|---|---|
| api | web service, port `8000` | `Dockerfile` | default; health check `/api/health`; **domain = the web domain, path `/api`** |
| worker | worker service | `Dockerfile` | `python -m app.worker` |
| scheduler | worker service | `Dockerfile` | `supercronic -passthrough-logs /app/crontab` |
| web | static site | build `npm ci && npm run build`, publish `dist` | — |
| database | managed database (PostgreSQL 16) | — | bind to api, worker and scheduler |
| queue | managed queue | — | bind to api, worker and scheduler |

Binding the database injects `DATABASE_URL`, and binding the queue injects `NATS_URL`, `NATS_USER` and `NATS_PASSWORD`; the app accepts them as-is. Set `DISPLAY_TIMEZONE=Asia/Jakarta` on api, worker and scheduler.

Give the api service the **web service's domain with ingress path `/api`**. The browser then calls the API on the same origin, so the web build's default `VITE_API_BASE_URL=/api` works and no CORS setup is needed. (NEO App's static-site build doesn't pass service variables into the build, so a build-time API URL can't be set there.)

Don't set `POSTGRES_*`, `FRONTEND_PORT`, `API_PORT` or `API_PROXY_TARGET` there; they only apply to local Docker Compose.

## Seed and reset

On first start, `init` seeds 250 fictional contacts (Indonesian names and businesses, all on the reserved `.example` domain), 12 completed campaigns spread over the last 30 days (with recipients, attempts, retries and activity, several within the last 7 days), 2 drafts, and one campaign scheduled a few minutes after setup.

Seeding is idempotent: it is guarded by an `app_meta` marker and an advisory lock. Restarting never erases your data or re-creates the demo schedule.

**Reset (destructive).** This deletes everything, including records you created, purges the queue, and reseeds. It asks you to type `reset` first and never runs automatically.

```bash
./scripts/reset-demo.sh
```

## Tests

```bash
make test        # docker compose run --rm --no-deps api python -m pytest -q tests
```

The tests run against a separate `pulse_test` database and cover dispatch claiming under concurrency, overlapping cron runs, cancel-versus-dispatch races, empty audiences, outbox leases and crash recovery, duplicate and redelivered messages, lease takeover, automatic retry timing, terminal failure, manual retry history and duplicate-run prevention, unsubscribe skipping, and exactly-once campaign completion.

## Two-minute walkthrough

1. Open http://localhost:3000. The **Dashboard** shows deliveries today, the 7-day success rate (hover ⓘ to see exactly how each metric is calculated), the volume chart, and the seeded campaign scheduled a few minutes out.
2. Click **Create campaign**. Enter a name, subject, and message (the preview updates as you type), and pick **VIP Customers**. The eligible count is a preview, because a scheduled campaign resolves its recipients when it's sent.
3. Choose **Schedule for later**, click **In 2 minutes** (or pick the next minute), then **Schedule campaign**. The detail page shows *Scheduled*. If you open it after the time passes but before cron runs, it shows *Awaiting scheduled dispatch*.
4. You can close the browser. When the minute arrives, Supercronic runs the dispatcher. Reopen the campaign to see recipients snapshotted, the live progress bar, and the activity timeline updating every 2 seconds.
5. Open **Job Activity**. Watch jobs move through *queued → processing → delivered*. A few go to *retrying* with a next-retry time, and some end *failed* after 3 attempts. The scheduler card shows the run that dispatched your campaign.
6. Back on the campaign, once it completes with failures, click **Retry N failed**. A new retry run starts. Click a recipient to see their full attempt history across both runs. Mailbox-full recipients now get through; hard bounces still fail.
7. Optional: on **Contacts**, unsubscribe someone who is part of a campaign that is still sending. Their pending delivery is **skipped**.

## Limitations

- Email is the only channel, and delivery is always simulated.
- The frontend runs the Vite dev server (good for local development, not a production build).
- One worker replica by default. More replicas are safe (`docker compose up --scale worker=2`) because claiming is lock-based.
- If a single campaign fails to dispatch repeatedly, the rest of that cron invocation stops. It is recorded as a failed run and retried the next minute.
