# parames

Paragliding wind alert tool — evaluates multi-model weather forecasts and sends alerts when conditions are favorable for ground handling.

Fetches hourly forecasts from [Open-Meteo](https://open-meteo.com/) across multiple NWP models, applies configurable wind direction/speed filters and optional plugins (Bise pressure check, laminar conditions), scores candidate windows, and delivers results via Telegram or the console.

## Architecture

| Component | Description |
|-----------|-------------|
| **CLI** (`parames run`) | One-shot evaluation and delivery |
| **Scheduler** | APScheduler cron job that calls `run` automatically |
| **API** | FastAPI REST backend (`/api/docs`) |
| **Web UI** | Vite-built frontend served from `webapp/dist/` |
| **MongoDB** | Persistence for alert definitions, detections, runs, and deliveries |

## Setup

Install Python dependencies:

```powershell
uv sync
```

## Local application environment

[Aspire](https://aspire.dev/) is the standard way to run the complete local Paramés environment. Install the Aspire CLI, Docker, and Node.js, then start the AppHost:

```sh
cd aspire
aspire restore
npm ci
export PARAMES_ADMIN_PASSWORD="$(openssl rand -base64 32)"
aspire start
```

Aspire starts MongoDB, creates the admin account `mail@manuelseeger.de`, assigns any legacy records in that Aspire database to the admin, then seeds alert definitions. Keep `PARAMES_ADMIN_PASSWORD` to log in during this session. The Aspire database is isolated from any existing Docker Compose database. `PARAMES_DEV_MODE=1` redirects deliveries to the console. Use the dashboard URL printed by `aspire start`, or inspect dynamically allocated API endpoints with:

```sh
aspire describe api --format Json
```

The scheduler is opt-in:

```sh
aspire resource scheduler start
```

To repeat the seed operation manually:

```sh
aspire resource api seed
aspire logs seed
```

Stop the local environment with `aspire stop`.

## Usage

Evaluate all configured alerts and deliver candidates:

```powershell
uv run parames run
uv run parames run --config config/default.yaml
```

### Backtest

Run evaluation on a past date without sending live alerts:

```powershell
uv run parames backtest --date 2025-04-15
uv run parames backtest --date 2025-04-15 --alert zurich_bise
uv run parames backtest --date 2025-04-15 --persist   # save results to DB for web UI review
```

### Capture

Capture Open-Meteo responses as replayable test fixtures:

```powershell
uv run parames capture                          # today (live API)
uv run parames capture --date 2025-04-15        # past date (historical API)
uv run parames capture --alert zurich_bise      # single alert profile
```

## Configuration

Alert profiles are defined in YAML. The default config is `config/default.yaml`.

Key sections:

- **`defaults`** — shared forecast settings (hours, wind level, model agreement thresholds)
- **`scoring`** — weights, emit threshold, and tier cutoffs (candidate / strong / excellent)
- **`alerts`** — list of alert profiles with location, models, wind filters, plugins, and delivery channels
- **`delivery_channels`** — named channels (`console`, `telegram`)
- **`scheduler`** — cron expression for the automated runner

## Environment variables

| Variable | Description |
|----------|-------------|
| `PARAMES_CONFIG_PATH` | Path to YAML config (default: `config/default.yaml`) |
| `PARAMES_MONGO_URI` | MongoDB connection string |
| `PARAMES_TELEGRAM_BOT_TOKEN` | Telegram bot token (required for Telegram delivery) |
| `PARAMES_DEV_MODE` | Set to `1` to redirect all delivery channels to console |
| `PARAMES_ADMIN_PASSWORD` | Initial admin password for `parames migrate-users`; a repeat run does not reset it |
| `PARAMES_COOKIE_SECURE` | Set to `1` behind HTTPS to mark the login cookie Secure |

## Deployment

Docker Compose remains in `deployment/` for the existing production deployment topology. Aspire owns the local application environment.

Docker Compose runs three services: `api`, `scheduler`, and `mongo`.

Before the first multi-user start, stop the API and scheduler and back up MongoDB. From the repository root, start only MongoDB with `docker compose -f deployment/docker-compose.yaml up -d mongo`, then run the migration:

```sh
export PARAMES_MONGO_URI='mongodb://localhost:27017/parames'
export PARAMES_ADMIN_PASSWORD="$(openssl rand -base64 32)"
uv run parames migrate-users
```

The command creates `mail@manuelseeger.de`, assigns legacy definitions and detections to that account, and replaces the old global name index. Repeating it does not reset the password or transfer owned records. Keep the initial password, then start the API and scheduler with `docker compose -f deployment/docker-compose.yaml up -d`. The API rejects databases that have not completed the migration.

The API and web UI are available on the host at `http://localhost:8090`. API docs are at `http://localhost:8090/api/docs`. The Compose port binds only to loopback. Put an HTTPS reverse proxy with signup and login rate limits in front of the API before you allow remote access. Set `PARAMES_COOKIE_SECURE=1` behind that proxy.

New accounts can sign up with an email address and password. Regular users can manage their own alert definitions and see their own detections. Their definitions use console delivery. Admin users can also use the dashboard, runs, logs, and configured delivery channels.

Set `PARAMES_TELEGRAM_BOT_TOKEN` in the environment or a `.env` file before starting.

## Tests

```powershell
uv run pytest -m "not integration"   # unit tests only (no network)
uv run pytest -m integration         # calls the live Open-Meteo API
```

To verify signup, ownership, and logout in an isolated Aspire app with `PARAMES_ADMIN_PASSWORD` set, run:

```sh
PARAMES_URL="$(cd aspire && aspire describe api --format Json | jq -r '.resources[0].urls[] | select(.name == "http") | .url')"
uv run --with playwright python tests/browser/verify_multiuser.py \
  --url "$PARAMES_URL" --artifacts ".pi/verification/parames/$(date -u +%Y%m%dT%H%M%SZ)/multiuser"
```

The browser check creates two regular accounts and alert definitions in that isolated database.
