# Detection Analysis and Deep Scoring Reports

## Overview

Each emitted `CandidateWindow` carries a full `EvaluationReport` in
`window.report`. That report is persisted with the detection document, returned
unchanged by the API, and rendered in the web UI Analysis tab.

The report is additive to the compact alert payload:

- `window.subscores` remains the compact per-signal view used in alert summaries
- `window.plugin_outputs` remains the compact per-plugin display payload
- `window.report` carries the deep trace used for debugging and tuning

## Report Models

### RuleEvaluation

Represents one scoring or gating rule evaluation.

```python
class RuleEvaluation(MainBaseModel):
    name: str
    observed: Any
    threshold: Any | None = None
    outcome: Literal["pass", "warn", "fail", "info"]
    delta: float | None = None
    message: str | None = None
```

### HourEvaluation

Represents the result of evaluating one timestamp in the forecast horizon.

```python
class HourEvaluation(MainBaseModel):
    time: datetime
    accepted: bool
    matching_models: list[str] = []
    rejection_reasons: list[str] = []
    rules: list[RuleEvaluation] = []
```

In the current implementation, `rejection_reasons` is populated, but the core
evaluator does not yet attach per-hour `rules`.

### ScoringTrace

Captures the weighted-mean assembly for the emitted window.

```python
class ScoringTrace(MainBaseModel):
    weights: dict[str, float]
    subscores: dict[str, float | None]
    contributions: dict[str, dict[str, Any]]
    weight_total: float
    weighted_sum: float
    raw_score: float | None
    final_score: int | None
    classification: Classification
    tiers: dict[str, int]
```

Each contribution entry includes:

- `weight`
- `sub_score`
- `weighted_value`
- `included`

### PluginReport

Represents the deep trace for one plugin.

```python
class PluginReport(MainBaseModel):
    type: str
    schema_version: int = 1
    summary: str | None = None
    config_snapshot: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    hourly: list[dict[str, Any]] = []
    rules: list[RuleEvaluation] = []
    notes: list[str] = []
```

The current built-in plugins both emit a `PluginReport`:

- Bise emits gradient, completeness, and threshold trace
- Laminar emits metric, penalty, and per-hour trace data

### Raw Forecast Snapshot

The full prefetched horizon is copied into the report as a list of
`ModelForecastSeries` entries, one per model. Numeric values are rounded before
storage.

### EvaluationReport

```python
class EvaluationReport(MainBaseModel):
    schema_version: int = 1
    profile_snapshot: dict[str, Any]
    horizon_start: datetime
    horizon_end: datetime
    forecast_models: list[str]
    hour_evaluations: list[HourEvaluation] = []
    raw_forecasts: list[ModelForecastSeries] = []
    scoring: ScoringTrace
    plugin_reports: list[PluginReport] = []
```

Notes:

- `raw_forecasts` is a list, not a dict
- `plugin_reports` is a list, not a keyed object
- validators accept older dict-shaped data and migrate it on read

## Generation Path

The report is assembled during evaluation:

1. `evaluation.core.evaluate` fetches per-model forecasts for the full horizon.
2. Every timestamp becomes a `HourEvaluation`, including hours outside the active horizon.
3. Accepted timestamps become `EvaluatedHour` entries.
4. `evaluation.scoring.score_window` computes built-in and plugin subscores.
5. The weighted-mean breakdown becomes `ScoringTrace`.
6. Plugin reports from `PluginScoringResult.report` are appended to `EvaluationReport.plugin_reports`.
7. The final report is attached to `CandidateWindow.report`.

## Current Hour-Level Reasons

The current evaluator can produce these rejection reasons at the hour level:

- `out_of_horizon`
- `min_models_matching_not_met`
- `model_agreement_failed`
- `missing_wind_data`

Model-level reasons such as `out_of_time_window` and
`wind_direction_out_of_range` are used internally by `evaluate_hour_reasons`,
but the current `HourEvaluation` stores only the aggregated timestamp-level
rejection reason.

## API and Persistence

The detection API returns the full persisted detection document, so
`window.report` is available through `GET /api/detections/{id}` without a
special diagnostics endpoint.

Because `Detection.window` stores the full `CandidateWindow`, the report is
also persisted automatically with the rest of the detection document in MongoDB.

## Web UI

The detection detail page exposes:

- `Overview` for the compact alert summary
- `Analysis` for the deep report

The Analysis tab currently renders these sections:

1. Score breakdown
2. Hour evaluation timeline
3. Raw forecasts, behind a collapsible section
4. Plugin reports, one card per plugin report
5. Profile snapshot, behind a collapsible section

If a detection has no report, the Analysis tab shows:

```text
No analysis report — re-run this alert to generate one.
```

## Scope of the Current Report

What the report already captures well:

- full scoring weights and contributions
- the final rounded score and underlying raw score
- the full raw forecast snapshot used during evaluation
- plugin-specific rule traces and per-hour intermediate values
- the resolved profile snapshot used for the run

What is intentionally still compact in the current implementation:

- `HourEvaluation.rules` is usually empty
- hour-level rejection causes are summarized at timestamp level rather than expanded into per-model rule rows

That compactness is part of the current contract and is what the UI renders
today.
