# Detection Analysis: Deep Scoring Reports

## Context

The detection scoring pipeline (`src/parames/evaluation/`) computes far more than it persists. Per-hour acceptance decisions, per-model raw forecasts, plugin intermediate metrics (gust factors, pressure deltas, model agreement deltas), aggregator weights and contributions, and gating decisions are all calculated and discarded. Today only `subscores` and a compact per-plugin `plugin_outputs` dict survive on the `CandidateWindow`.

A developer fine-tuning the scoring rules needs to see, for any persisted Detection, the full chain that produced its final score: which hours got in (and which were rejected and why), the raw forecast values per model, every intermediate metric per plugin, every rule that fired and how much it cost, and exactly how the weighted-mean was assembled.

The goal is a future-proof report contract baked into the evaluation pipeline so every plugin (current and future) can ship a structured trace; ship it with the Detection over the API; and render it in a new "Analysis" tab on the detection detail view that discloses everything.

---

## Future-proof reporting model

A single `EvaluationReport` is attached to `CandidateWindow.report` (so it persists in `Detection.window.report` automatically via pyodmongo) and ships over the existing `GET /detections/{id}` endpoint without an API change. New types, all in [domain.py](src/parames/domain.py):

```
class RuleEvaluation(MainBaseModel):
    name: str                  # e.g. "gust_factor", "model_agreement", "wind_in_range"
    observed: Any              # raw value the rule looked at
    threshold: Any | None      # config threshold(s) compared against
    outcome: Literal["pass", "warn", "fail", "info"]
    delta: float | None = None # +/- contribution to a score, when applicable
    message: str | None = None # human-readable explanation

class HourEvaluation(MainBaseModel):
    time: datetime
    accepted: bool
    matching_models: list[str]
    rejection_reasons: list[str] = []   # e.g. "out_of_time_window", "wind_below_min"
    rules: list[RuleEvaluation] = []    # per-hour gating trace

class ScoringTrace(MainBaseModel):
    weights: dict[str, float]
    subscores: dict[str, float | None]
    contributions: dict[str, dict[str, float | None]]   # name -> {weight, sub_score, weighted_value}
    weight_total: float
    weighted_sum: float
    raw_score: float | None
    final_score: int | None
    classification: Classification
    tiers: dict[str, int]               # snapshot of tier thresholds used

class PluginReport(MainBaseModel):
    type: str                           # plugin type tag
    schema_version: int = 1
    summary: str | None = None
    config_snapshot: dict[str, Any] = {}
    inputs: dict[str, Any] = {}         # which models, sources, etc.
    metrics: dict[str, Any] = {}        # aggregate values
    hourly: list[dict[str, Any]] = []   # per-hour intermediate values
    rules: list[RuleEvaluation] = []    # ordered trace of every rule
    notes: list[str] = []

class ModelHourForecast(MainBaseModel):
    time: datetime
    wind_speed: float | None = None
    wind_direction: float | None = None
    wind_gusts: float | None = None
    precipitation: float | None = None
    pressure_msl: float | None = None
    cape: float | None = None
    showers: float | None = None

class EvaluationReport(MainBaseModel):
    schema_version: int = 1
    profile_snapshot: dict[str, Any]                     # frozen at-eval profile config (wind, agreement, plugins)
    horizon_start: datetime
    horizon_end: datetime
    forecast_models: list[str]
    hour_evaluations: list[HourEvaluation]               # only inside the report's context window range
    raw_forecasts: dict[str, list[ModelHourForecast]]    # per-model, full prefetch horizon
    scoring: ScoringTrace
    plugin_reports: dict[str, PluginReport]
```

Scope: `raw_forecasts` and `hour_evaluations` cover the **full prefetch horizon** (every timestamp the forecast client returned for any contributing model), so the Analysis tab can explain why every nearby hour was accepted or rejected. Floats are rounded to 2-3 dp at serialization time to keep document size reasonable.

The plugin protocol in [base.py](src/parames/plugins/base.py) replaces the current `tuple[float | None, dict[str, Any]]` return shape with a single result dataclass:

```
class PluginScoringResult(MainBaseModel):
    sub_score: float | None
    output: dict[str, Any] = {}        # the existing compact "plugin_outputs" payload
    report: PluginReport | None = None # deep diagnostic
```

Both registered plugins (Bise, Laminar) are updated to the new return type. The aggregator unpacks `result.sub_score` for weighting, copies `result.output` into `CandidateWindow.plugin_outputs[type]` (preserving the current Overview tab contract), and stores `result.report` in `EvaluationReport.plugin_reports[type]`.

---

## Backend work

### 1. Add the report types
- Append `RuleEvaluation`, `HourEvaluation`, `ScoringTrace`, `PluginReport`, `ModelHourForecast`, `EvaluationReport` to [domain.py](src/parames/domain.py).
- Add `report: EvaluationReport | None = None` to `CandidateWindow` (line 40-68). pyodmongo will recurse and persist it automatically through the existing `Detection.window` field — no change needed in [persistence/models.py](src/parames/persistence/models.py).

### 2. Replace plugin protocol return type
- In [base.py](src/parames/plugins/base.py:45-51), define `PluginScoringResult(MainBaseModel)` with `sub_score`, `output`, `report` and change `score_window`'s return type to `PluginScoringResult`.
- Update Bise and Laminar to return a `PluginScoringResult` instead of a tuple.
- Update the aggregator in [scoring.py](src/parames/evaluation/scoring.py:142-149) to call the new method, store `result.output` in `CandidateWindow.plugin_outputs`, and `result.report` in `EvaluationReport.plugin_reports`.

### 3. Refactor scoring to capture trace + plugin reports
- In [scoring.py](src/parames/evaluation/scoring.py:106-181) `score_window`:
  - For each subscore, record `(weight, sub_score, weighted_value, included)` into a contributions dict.
  - Add wind_speed and wind_duration `RuleEvaluation` entries (with their config thresholds: `min_speed_kmh`, `strong_speed_kmh`, `min_consecutive_hours`).
  - Build `ScoringTrace` with `weight_total`, `weighted_sum`, `raw_score`, `final_score`, `tiers`.
  - Collect plugin reports from each `PluginScoringResult.report`.
- Pass through `accepted_hours` evaluation traces (gathered upstream) and the profile snapshot, then build the `EvaluationReport` and attach it to the returned `CandidateWindow`.

### 4. Capture acceptance trace in core
- In [core.py](src/parames/evaluation/core.py:78-91) replace the simple `if evaluated is not None: accepted_hours.append(evaluated)` with a path that always records a `HourEvaluation` (accepted or rejected) for **every timestamp the forecast client returned** (the full prefetched horizon).
- Refactor [_evaluate_timestamp](src/parames/evaluation/core.py:109-156) so it returns `(EvaluatedHour | None, list[str] reasons, list[RuleEvaluation] rules)` rather than just the optional `EvaluatedHour`. Reasons come from existing branch points: `out_of_horizon`, `out_of_time_window`, `wind_below_min`, `wind_direction_out_of_range`, `dry_filter_failed`, `min_models_matching_not_met`, `model_agreement_failed`, `missing_wind_data`. Reuse [evaluate_hour_candidate](src/parames/evaluation/wind.py:12-29) but make its boolean returns into structured outcomes (extract a sibling helper that returns `(bool, list[str])`).
- Snapshot raw forecasts for the **full prefetch horizon** — convert each `dict[datetime, HourForecast]` per model into a sorted list of `ModelHourForecast`. Round floats to 2-3 dp.
- Snapshot the profile config via `profile.model_dump()` into `EvaluationReport.profile_snapshot`.

### 5. Make Bise emit a report
- [bise.py](src/parames/plugins/bise.py:68-104) currently produces `{"gradient_hpa": gradient}` and a sub_score. Add a `PluginReport`:
  - `inputs`: `{"contributing_models": [...], "west_location": ..., "east_location": ...}`
  - `metrics`: `{"avg_gradient_hpa", "min_gradient_hpa", "max_gradient_hpa"}`
  - `hourly`: per-timestamp `{time, per_model_gradient_hpa: {model: float}, mean_gradient_hpa}`
  - `rules`: `RuleEvaluation` for `gradient_threshold` (observed=gradient, threshold=`east_minus_west_pressure_hpa_min`, outcome `pass/warn/fail`, message), and `data_completeness` (any timestamp missing).

### 6. Make Laminar emit a report
- [laminar.py](src/parames/plugins/laminar.py:156-436) currently builds an ad-hoc `reasons[]` list with truncation (`reasons[:6]`) and a flat `metrics` dict. Convert each existing branch into a `RuleEvaluation`:
  - `gust_factor` (observed=`max_gust_factor`, thresholds=`good_max`, `marginal_max`, delta=`-15`/`-35`)
  - `gust_spread` (delta=`-10`/`-25`)
  - `direction_variability`
  - `speed_range`
  - `cape` (with availability gate as a sibling info rule)
  - `precipitation`, `showers`
  - `pressure_tendency` (with the fallback-scaling note attached as `message`)
  - `model_agreement` (observed=`{"dir_delta", "speed_delta"}`, with secondary-model resolution recorded as an info rule)
  - `primary_model_resolution`, `secondary_model_resolution` info rules
- `hourly` records the per-hour `gust_factor`, `gust_spread`, raw wind/gust/cape/pressure for both primary and secondary, plus per-hour `dir_delta`/`speed_delta`.
- `metrics` keeps the current aggregate values (so the existing compact `plugin_outputs` view still works) plus full unrounded values for the analysis tab.
- Keep returning the existing `plugin_outputs` dict unchanged so the current Overview tab is unaffected — this is purely additive.

### 7. Plumb reports out unchanged via API
- [detections.py](src/parames/api/routers/detections.py) already returns the full `Detection` model — `window.report` flows through automatically. Verify the Pydantic schema is exported and validate the response shape with a smoke test.

### 8. Dev-mode runtime cost guard
- Build the report unconditionally (the cost is dominated by forecast fetches that already happened). Doc size grows with horizon × models — keep floats rounded to 2-3 dp and only include fields the plugins/evaluator actually use. For a 48h horizon × 4 models × 8 numeric fields this is well under the MongoDB 16 MB doc limit.

### 9. Backend tests
Add to [tests/](tests/):
- `test_scoring_trace.py`: a `score_window` call with a known set of subscores produces the expected `ScoringTrace.contributions`, `weight_total`, and `raw_score`; verify `final_score == round(weighted_sum / weight_total)` clamped to `[0, 100]`.
- `test_hour_evaluation_trace.py`: feed in a fixture with one of each rejection reason and assert the right strings land in `HourEvaluation.rejection_reasons`.
- `test_bise_report.py` and extend `tests/test_laminar.py` with a `test_laminar_report.py`: assert each rule fires with the expected delta and outcome on a crafted forecast.
- Round-trip test: serialize a `Detection` with full report through pyodmongo and back, confirm fields survive.

---

## Frontend work

### 1. Tabs on DetectionDetail.vue
- Convert [DetectionDetail.vue](webapp/src/views/DetectionDetail.vue:188-437) into a tabbed layout (`Overview`, `Analysis`). The Analysis tab is **always visible** to all users. Tab state held in a `ref('overview')`. Existing template moves under the `Overview` tab unchanged.
- Add a small tab strip styled to match existing pills (use `pill-*` classes from [styles.css](webapp/src/styles.css)).
- Defensive guard: when `detection.window.report` is `null` (legacy detection saved before the report system existed), the Analysis tab shows an empty-state placeholder: "No analysis report — re-run this alert to generate one." No regenerate button or backfill.

### 2. Analysis tab content
Top-to-bottom in a new component `webapp/src/views/detection/AnalysisTab.vue`:

1. **Final score breakdown** — `ScoringBreakdown.vue`
   - Horizontal stacked bar: each contribution sized by `weight × sub_score`.
   - Below: a table with columns `Signal | Weight | Sub-score | Weighted | Included`. Mark opted-out signals (`null`) distinctly.
   - Sum row: `weight_total`, `weighted_sum`, `raw_score`, `final_score (clamped & rounded)`, `classification` pill, with the `tiers` shown as horizontal markers on a 0-100 scale.

2. **Hour evaluation timeline** — `HourTimeline.vue`
   - One row per hour across the full prefetched horizon. For each hour: timestamp, accepted/rejected pill, matching models count, rejection reasons as small chips, expandable details showing each `RuleEvaluation` row (name, observed, threshold, outcome).
   - Visually mark the in-window range so devs can see which rejected hours are adjacent to the alert window.

3. **Raw forecasts per model** — `ModelForecastTable.vue`
   - Wide table: rows = hours across full horizon, columns grouped by model, sub-columns wind/gust/dir/precip/pressure/cape (only show columns where any model has data).
   - Sticky header, monospace numerics, color-coded cells (rejected hours dim, accepted highlighted, in-window rows banded).
   - For long horizons, the body is scrollable so the table doesn't dominate the viewport.

4. **Plugin reports** — one collapsible card per `plugin_reports` entry, rendered by `PluginReportCard.vue`:
   - Header: plugin type, summary line.
   - **Config snapshot**: `MetricsGrid.vue` rendering `config_snapshot`.
   - **Inputs**: `MetricsGrid.vue` rendering `inputs`.
   - **Aggregate metrics**: `MetricsGrid.vue` rendering `metrics`.
   - **Rules**: `RulesTable.vue` — columns `Rule | Observed | Threshold | Outcome | Δ | Message`, color-coded by outcome.
   - **Hourly trace**: collapsible table generated dynamically from the union of keys in `hourly[]`.
   - **Notes**: list.

5. **Profile snapshot** — collapsible JSON-style key-value tree (`ConfigTree.vue`) of `profile_snapshot`.

### 3. Reusable presentational components
All under `webapp/src/views/detection/`:
- `AnalysisTab.vue` — orchestrator
- `ScoringBreakdown.vue` — stacked bar + breakdown table
- `HourTimeline.vue` — per-hour acceptance trace
- `ModelForecastTable.vue` — per-model wide table
- `PluginReportCard.vue` — generic plugin report renderer
- `RulesTable.vue` — generic rules table
- `MetricsGrid.vue` — generic key-value renderer
- `ConfigTree.vue` — collapsible JSON tree

These are fully driven by the report shape, so adding a new plugin in the future requires no frontend change — its `PluginReport` simply renders through `PluginReportCard.vue`.

### 4. Styling
Reuse existing tokens from [styles.css](webapp/src/styles.css). Add a small section for tabs, monospace numeric tables, and outcome color coding (`pass`=green, `warn`=amber, `fail`=red, `info`=neutral).

### 5. No API client change
[api.js](webapp/src/api.js:45) `getDetection(id)` already returns the full Detection — `window.report` flows through.

### 6. Frontend verification
- After backend lands, trigger a fresh run via the dashboard or `POST /runs` and confirm a new Detection has `window.report` populated.
- Use the playwright-cli skill to load `/#/detections/{id}`, switch to Analysis tab, and assert each section renders for a real Bise+Laminar detection.

---

## Critical files

Backend:
- [src/parames/domain.py](src/parames/domain.py) — add report types, attach `report` to `CandidateWindow`.
- [src/parames/plugins/base.py](src/parames/plugins/base.py) — extend protocol return type.
- [src/parames/plugins/bise.py](src/parames/plugins/bise.py) — emit `PluginReport`.
- [src/parames/plugins/laminar.py](src/parames/plugins/laminar.py) — emit `PluginReport`.
- [src/parames/evaluation/scoring.py](src/parames/evaluation/scoring.py) — build `ScoringTrace` + `EvaluationReport`.
- [src/parames/evaluation/core.py](src/parames/evaluation/core.py) — capture `HourEvaluation`s and raw forecasts, profile snapshot.
- [src/parames/evaluation/wind.py](src/parames/evaluation/wind.py) — refactor `evaluate_hour_candidate` to return reasons.
- [tests/](tests/) — new tests as listed.

Frontend:
- [webapp/src/views/DetectionDetail.vue](webapp/src/views/DetectionDetail.vue) — add tabs.
- `webapp/src/views/detection/*.vue` — new components.
- [webapp/src/styles.css](webapp/src/styles.css) — small additions for tabs and outcome colors.

---

## Verification

1. **Unit tests**: `uv run pytest` — all new tests green.
2. **Local end-to-end**:
   ```
   PARAMES_DEV_MODE=true uv run uvicorn parames.api:app --host 0.0.0.0 --port 7000
   ```
   Trigger a run via the dashboard. Inspect the new detection JSON via `GET /detections/{id}` and confirm:
   - `window.report.scoring` has `contributions`, `weight_total`, `raw_score`, `final_score` matching `window.score`.
   - `window.report.hour_evaluations` lists every hour in the context range with rejection reasons where applicable.
   - `window.report.plugin_reports.bise` and `window.report.plugin_reports.laminar` each have populated `rules`, `metrics`, and `hourly`.
3. **Frontend**: Use playwright-cli to load `/#/detections/{id}`, click the Analysis tab, and visually verify all six sections render with data. For an old detection (no report) verify the friendly placeholder.
4. **Backwards compatibility**: pre-existing detections without `report` still load and render the Overview tab unchanged.
