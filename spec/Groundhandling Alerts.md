# Paragliding Groundhandling Alert System

## Overview

The application evaluates forecast models for configured groundhandling sites,
scores contiguous wind windows, stores detections in MongoDB, and delivers
them through console and Telegram channels. The same persisted detections are
served through the FastAPI backend and rendered in the web UI.

The current default configuration defines three alert profiles:

- `schoenberg` for northerly groundhandling conditions near Freiburg
- `mainz_finthen` for broad wind-supported groundhandling windows
- `zurich_bise` for Zurich Bise conditions, with both the Bise and Laminar plugins enabled

## Runtime Surfaces

### Evaluation

The evaluation pipeline is a library call:

```python
evaluate(profile: AlertProfileConfig) -> list[CandidateWindow]
```

For one resolved alert profile it:

1. Fetches the core hourly forecast for each configured model.
2. Runs per-timestamp acceptance checks.
3. Groups accepted hours into contiguous windows.
4. Computes a weighted composite score from built-in and plugin subscores.
5. Attaches an `EvaluationReport` with hour-level, model-level, and plugin-level trace data.
6. Returns only windows whose final score meets `scoring.emit_threshold`.

### Runner

The runner loads alert definitions from MongoDB, resolves defaults from YAML,
evaluates each profile, upserts matching detections, and delivers unsuppressed
results. Duplicate suppression is channel-aware and defaults to enabled for
non-console channels.

### API and Web App

The FastAPI app exposes:

- `/api/health`
- `/api/alert_definitions`
- `/api/detections`
- `/api/runs`
- `/api/deliveries`

When a built frontend exists in `webapp/dist`, it is mounted at `/` by the
same FastAPI process.

## Current Configuration Shape

The YAML configuration contains:

- `defaults` for forecast horizon, wind level, model agreement, and wind scoring defaults
- `scoring` for weights, emit threshold, and classification tiers
- `alerts` as a list of alert profiles
- `delivery_channels` for named console or Telegram channels
- `scheduler` for cron-like run cadence

The shipped default config currently looks like this structurally:

```yaml
defaults:
  forecast_hours: 48
  wind_level_m: 10
  model_agreement:
    required: true
    min_models_matching: 2
    max_direction_delta_deg: 35
    max_speed_delta_kmh: 8.0
  wind:
    min_speed_kmh: 10.0
    strong_speed_kmh: 28.0
    sweet_spot_kmh: 20.0
    sweet_spot_sigma_kmh: 7.0

scoring:
  weights:
    wind_speed: 2.0
    plugins:
      bise: 0.7
      laminar: 0.7
  emit_threshold: 50
  tiers:
    candidate_min: 60
    strong_min: 70
    excellent_min: 85

alerts:
  - name: schoenberg
    plugins:
      - type: laminar
  - name: mainz_finthen
    plugins:
      - type: laminar
  - name: zurich_bise
    plugins:
      - type: bise
      - type: laminar

delivery_channels:
  console:
    type: console
  telegram:
    type: telegram

scheduler:
  cron_hour: "*/6"
```


## Forecast Inputs

The core evaluator fetches, per model:

- `wind_speed_{wind_level_m}m`
- `wind_direction_{wind_level_m}m`
- `precipitation`
- `pressure_msl`

Plugins may fetch additional variables for the same horizon. Laminar fetches
gusts, showers, CAPE, and pressure at its configured wind level. Bise fetches
pressure for separate east and west reference locations.

All timestamps are handled in the Zurich timezone.

## Per-Hour Acceptance

Each timestamp is evaluated independently across models.

### Model-Level Gate

A model contributes a matching hour when all of the following are true:

1. The hour is within the configured `time_window`, if one is set.
2. `wind_speed >= wind.min_speed_kmh`.
3. `wind_direction` falls inside `[direction_min_deg, direction_max_deg]`, using circular range logic.

The `dry` config block is part of the profile schema and is persisted in alert
definitions and reports, but it is not currently applied by the hour-gating
logic. Precipitation is still fetched, stored, charted, and used by plugins.

### Agreement Gate

A timestamp is accepted only when at least
`model_agreement.min_models_matching` models passed the model-level gate.

If `model_agreement.required` is true, every pair of matching models must also
agree on:

- angular direction delta `<= max_direction_delta_deg`
- absolute speed delta `<= max_speed_delta_kmh`

If the timestamp passes, the evaluator stores:

- average wind speed across matching models
- maximum wind speed across matching models
- vector-averaged wind direction across matching models
- average precipitation across matching models when present

If it fails, the report stores one of the current rejection reasons:

- `out_of_horizon`
- `min_models_matching_not_met`
- `model_agreement_failed`
- `missing_wind_data`

## Window Construction

Accepted timestamps are sorted and merged into contiguous one-hour runs.
Only runs with at least `wind.min_consecutive_hours` survive as candidate
windows.

After scoring, the UI-facing `hours` series on each emitted window is extended
with up to two context hours before and after the alert window when forecast
data exists.

## Scoring

### Built-In Subscore

The only built-in subscore is `wind_speed`. It is a Gaussian curve centered on
`wind.sweet_spot_kmh` with width `wind.sweet_spot_sigma_kmh`, computed per hour
and averaged across the window.

```python
score_hour = exp(-0.5 * ((speed - sweet_spot_kmh) / sweet_spot_sigma_kmh) ** 2) * 100
wind_speed_subscore = average(score_hour over window)
```

There is no separate built-in duration subscore in the current implementation.
Window duration only acts as a hard minimum through `min_consecutive_hours`.

### Plugin Subscores

Each enabled plugin returns a `PluginScoringResult`:

```python
class PluginScoringResult(MainBaseModel):
    sub_score: float | None
    output: dict[str, Any] = {}
    report: Any | None = None
```

- `sub_score` participates in the weighted mean when not `None`
- `output` is copied to `CandidateWindow.plugin_outputs[plugin_type]` when non-empty
- `report` is appended to `EvaluationReport.plugin_reports`

### Aggregation

The composite window score is a weighted mean over all included subscores:

```text
final = round(sum(weight * sub_score) / sum(weight))
```

Signals with `sub_score = None` are excluded from both numerator and
denominator. Unknown plugin weights fall back to `1.0` with a warning.

The shipped scoring weights are:

| Signal | Weight |
|---|---|
| `wind_speed` | `2.0` |
| `bise` | `0.7` |
| `laminar` | `0.7` |

### Classification

The final rounded composite is classified as:

| Score | Classification |
|---|---|
| `None` | `unavailable` |
| `< 60` | `weak` |
| `60-69` | `candidate` |
| `70-84` | `strong` |
| `>= 85` | `excellent` |

Only windows with `score >= 50` are emitted.

## Candidate Window Model

Each emitted `CandidateWindow` carries:

- alert metadata and contributing model list
- start, end, and duration
- average and maximum wind speed
- average direction
- average and maximum precipitation when available
- per-signal `subscores`
- compact `plugin_outputs`
- a full `EvaluationReport`

The `EvaluationReport` contains:

- `profile_snapshot`
- `horizon_start` and `horizon_end`
- `forecast_models`
- `hour_evaluations`
- `raw_forecasts`
- `scoring`
- `plugin_reports`

The current report format is described in [Deep scoring reports.md](./Deep%20scoring%20reports.md).

## Delivery

### Console

Console delivery renders:

- score classification and numeric score
- per-signal subscores that participated in scoring
- average and maximum wind speed
- average direction
- Bise gradient when the Bise plugin is configured
- Laminar label and up to three reasons when the Laminar plugin is configured
- precipitation summary
- an ASCII chart for the window and context hours

### Telegram

Telegram delivery renders the same core information in MarkdownV2, including:

- the Bise gradient when available
- the Laminar label plus up to three reasons
- a monospaced chart block

In development mode, non-console channels are redirected to console delivery.

## Persistence

The production app persists data in MongoDB through `pyodmongo` models.

Collections:

- `alert_definitions`
- `runs`
- `detections`
- `deliveries`

Detections store the full `CandidateWindow`, including `plugin_outputs` and the
full `window.report` tree. That same document shape is returned by the API and
consumed by the web app.

## Web UI

The detection detail view has two tabs:

- `Overview` for the compact alert summary
- `Analysis` for the deep evaluation report

When a legacy detection has no `window.report`, the Analysis tab shows a
placeholder prompting the user to re-run the alert.

## Plugin Specs

Plugin-specific behavior is documented separately:

- [Bise Plugin.md](./Bise%20Plugin.md)
- [Laminar Plugin.md](./Laminar%20Plugin.md)
