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

Install dependencies:

```powershell
uv sync
```

Before first run, seed alert definitions from YAML into MongoDB:

```powershell
uv run parames seed
uv run parames seed --config config/default.yaml  # explicit path
```

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

## Deployment

Docker Compose runs three services: `api`, `scheduler`, and `mongo`.

```powershell
cd deployment
docker compose up -d
```

The API and web UI are available at `http://localhost:8090`. API docs at `http://localhost:8090/api/docs`.

Set `PARAMES_TELEGRAM_BOT_TOKEN` in the environment or a `.env` file before starting.

## Tests

```powershell
uv run pytest -m "not integration"   # unit tests only (no network)
uv run pytest -m integration         # calls the live Open-Meteo API
```
