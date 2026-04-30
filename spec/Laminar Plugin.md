# Laminar Wind Scoring Plugin — Technical Spec

## Purpose

Add a laminar-quality score to candidate wind windows produced by the existing
alert pipeline.

The plugin does **not** decide whether wind direction/speed is suitable —
that is the alert profile's job ([evaluation.py:49](../src/parames/evaluation.py#L49)).
It scores whether an already-accepted window is likely to be:

- stable
- smooth
- non-gusty
- non-convective
- model-consistent

The rich result (0–100 score, label, reasons, metrics) is stored in
`CandidateWindow.plugin_outputs["laminar"]`. The 0–100 sub-score is also
returned as the plugin's contribution to the composite window score, which
is computed as a weighted mean of all active signals.

---

## 1. Integration with the existing plugin system

The plugin implements the `EvaluationPlugin` protocol
([plugins/base.py:20](../src/parames/plugins/base.py#L20)) and follows the
same shape as `BisePlugin` ([plugins/bise.py](../src/parames/plugins/bise.py)).

### Lifecycle (per evaluation run)

1. **Construction** — instantiated by `build_plugins()` from a
   `LaminarPluginConfig` parsed out of the alert profile's `plugins:` list.
2. **`prefetch(client, models)`** — fetches gusts / CAPE / showers / pressure
   for the alert location, for every model in the alert profile, over the
   full forecast horizon. Returns a `LaminarPrefetched` cache.
3. **`score_window(window_times, prefetched, contributing_models)`** — called
   once per surviving `CandidateWindow`. Returns
   `(sub_score: float | None, output: dict)`.

### Score interaction with the weighted-mean aggregator

Laminar is a **quality signal**. It always returns its 0–100 sub-score when
the required wind/gust data is present — even a poor window (score 10)
drags the composite down proportionally rather than opting out. The only
case where it returns `None` is when `wind_speed`, `wind_direction`, or
`wind_gusts` is missing for any hour in the primary model (see §8).

The composite score in
[`evaluation.py`](../src/parames/evaluation.py) is computed as:

```
composite = round( Σ(wᵢ · sᵢ) / Σ(wᵢ) )   over i where sᵢ is not None
```

Laminar's weight is read from global config at
`scoring.weights.plugins.laminar` (default **1.0**). The weight lives in
`config/default.yaml`, not on the plugin or the alert profile.

| Laminar present? | Effect |
|---|---|
| Sub-score returned (0–100) | Contributes to weighted mean at weight 1.0 |
| `None` (missing required data) | Excluded from numerator and denominator; remaining signals renormalize |

A "poor" laminar window (e.g. sub-score 20) lowers the composite in
proportion to its weight. A borderline candidate with good wind but poor
laminar will have its score pulled toward the threshold and may fall below
`scoring.emit_threshold` (40) — this is the intended suppression mechanism,
without any special-case runner logic.

### Output dict (persisted to `CandidateWindow.plugin_outputs["laminar"]`)

```json
{
  "score": 82,
  "label": "good",
  "reasons": [
    "low_gust_factor",
    "stable_direction",
    "low_cape",
    "model_agreement_good"
  ],
  "metrics": {
    "avg_gust_factor": 1.31,
    "max_gust_spread_kmh": 6.2,
    "direction_variability_deg": 18,
    "speed_range_kmh": 4.1,
    "max_cape": 35,
    "model_direction_delta_deg": 22,
    "model_speed_delta_kmh": 4.8,
    "pressure_tendency_3h_hpa": 0.7
  },
  "primary_model": "icon_d2",
  "secondary_model": "ecmwf_ifs"
}
```

When required wind data is missing the plugin returns
`(None, {"score": null, "label": "unavailable", "reasons": ["missing_required_wind_data"]})`.
The `None` sub-score causes the aggregator to exclude laminar entirely from
the composite calculation for that window.

---

## 2. Configuration

```yaml
plugins:
  - type: laminar
    enabled: true

    # Optional: override the wind level used by the plugin's gust/wind reads.
    # Defaults to the alert profile's wind_level_m.
    wind_level_m: null

    # Model selection for primary / secondary signals.
    # Resolved at score time against contributing_models for the window.
    # If null, defaults to contributing_models[0] / contributing_models[1].
    primary_model: icon_d2          # optional
    secondary_model: ecmwf_ifs      # optional

    gust_factor:
      good_max: 1.35
      marginal_max: 1.60

    gust_spread_kmh:
      good_max: 6.0
      marginal_max: 10.0

    direction_variability_deg:
      good_max: 20
      marginal_max: 40

    speed_range_kmh:
      good_max: 4.0
      marginal_max: 7.0

    cape_j_kg:
      good_max: 50
      marginal_max: 200

    model_agreement:
      direction_good_max_deg: 25
      direction_marginal_max_deg: 40
      speed_good_max_kmh: 5
      speed_marginal_max_kmh: 8

    pressure_tendency_3h_hpa:
      good_max_abs: 1.5
      marginal_max_abs: 2.5

    precipitation:
      max_precip_mm_h: 0.0
      max_showers_mm_h: 0.0
```

### Pydantic model (sketch)

```python
# src/parames/plugins/laminar.py

class GustFactorThresholds(MainBaseModel):
    good_max: float = 1.35
    marginal_max: float = 1.60

# ... one per metric ...

class LaminarPluginConfig(PluginConfigBase):
    type: Literal["laminar"] = "laminar"
    wind_level_m: int | None = None
    primary_model: str | None = None
    secondary_model: str | None = None
    gust_factor: GustFactorThresholds = Field(default_factory=GustFactorThresholds)
    gust_spread_kmh: GustSpreadThresholds = Field(default_factory=GustSpreadThresholds)
    direction_variability_deg: DirectionVariabilityThresholds = ...
    speed_range_kmh: SpeedRangeThresholds = ...
    cape_j_kg: CapeThresholds = ...
    model_agreement: LaminarModelAgreement = ...
    pressure_tendency_3h_hpa: PressureTendencyThresholds = ...
    precipitation: PrecipThresholds = ...
```

The config must be added to the discriminated union in
[plugins/schemas.py](../src/parames/plugins/schemas.py):

```python
PluginConfig = Annotated[
    Union[BisePluginConfig, LaminarPluginConfig],
    Field(discriminator="type"),
]
```

…and re-exported from [plugins/__init__.py](../src/parames/plugins/__init__.py).

---

## 3. Data fetched by the plugin

The core pipeline only fetches `wind_speed`, `wind_direction`,
`precipitation`, `pressure_msl` ([forecast.py:107-112](../src/parames/forecast.py#L107-L112)).
The laminar plugin's `prefetch` issues additional requests for the
**alert location**, for **every model in the alert profile**, over the full
forecast horizon (`forecast_days=3` to match the core fetch):

| Variable | Required? | Notes |
|---|---|---|
| `wind_gusts_{level}m` | required | Open-Meteo exposes gust at the same wind level. |
| `cape` | optional | Not all models expose CAPE (e.g. `meteoswiss_icon_ch2` may omit). Treat as missing → skip CAPE penalty + add `cape_unavailable` reason. |
| `showers` | optional | Some models only return `precipitation`. Treat absence as `0`; emit `showers_unavailable` reason only if neither `showers` nor `precipitation` exist for that model. |
| `wind_speed_{level}m`, `wind_direction_{level}m`, `precipitation`, `pressure_msl` | re-fetched | Already fetched by core; re-fetched here to keep the plugin self-contained. Known minor inefficiency — see §8. |

The plugin reuses the alert profile's `wind_level_m` unless overridden.

### `LaminarPrefetched` shape

```python
class LaminarHour(MainBaseModel):
    time: datetime
    wind_speed: float | None
    wind_direction: float | None
    wind_gusts: float | None
    precipitation: float | None
    showers: float | None
    cape: float | None
    pressure_msl: float | None

# keyed by model → time → LaminarHour
LaminarPrefetched = dict[str, dict[datetime, LaminarHour]]
```

Pressure data covers the full horizon so `score_window` can compute
`pressure_msl[t+3h] - pressure_msl[t]` even at the window's tail.

---

## 4. Metric definitions

All metrics computed from the **primary model** unless stated.

### 4.1 Gust factor

Per hour:
```
gust_factor = wind_gusts / max(wind_speed, 1)
gust_spread_kmh = wind_gusts - wind_speed
```

Window:
```
avg_gust_factor, max_gust_factor
avg_gust_spread_kmh, max_gust_spread_kmh
```

### 4.2 Direction stability

Use circular math (already in [evaluation.py](../src/parames/evaluation.py#L35)
— reuse `angular_distance` and `vector_average_direction`).

```
mean_dir = vector_average_direction([h.wind_direction for h in window])
direction_variability_deg = max(angular_distance(h.wind_direction, mean_dir)
                                for h in window)
```

This replaces the spec's pairwise O(N²) approach: linear cost, more stable
near 360°/0° wraps, and reuses existing helpers.

### 4.3 Speed stability

```
speed_range_kmh = max(wind_speed) - min(wind_speed)
gust_range_kmh  = max(wind_gusts) - min(wind_gusts)
```

### 4.4 Convective risk

```
max_cape, avg_cape   # primary model
```

If `cape` is missing for >50% of window hours → treat as missing → skip
penalty, add `cape_unavailable` reason.

### 4.5 Precipitation / shower risk

```
max_precipitation = max over window (primary model)
max_showers       = max over window (primary model, 0 if missing)
```

If `max_precipitation > 0` or `max_showers > 0` → strong penalty.

### 4.6 Model agreement (primary vs secondary)

Per timestamp in window:
```
speed_delta     = abs(p.wind_speed - s.wind_speed)
direction_delta = angular_distance(p.wind_direction, s.wind_direction)
gust_delta      = abs(p.wind_gusts - s.wind_gusts)
```

Score against the 75th percentile (or `max` if window <4h) of each delta —
catches a single hour of disagreement without being dominated by it.

If secondary model is unavailable (not in `contributing_models` and not in
prefetched cache), apply a flat **penalty 10** and add reason
`secondary_model_unavailable`.

### 4.7 Pressure stability

```
pressure_tendency_3h_hpa = pressure_msl[window_start + 3h] - pressure_msl[window_start]
```

If the window starts within 3h of the forecast horizon end, fall back to:
```
pressure_tendency_3h_hpa = (last_pressure - first_pressure) * (3h / window_duration_h)
```

`max_abs_pressure_tendency_3h_hpa` is the metric used for scoring. This is a
stability signal, not a wind-direction signal.

---

## 5. Penalties

Start `score = 100`, subtract:

| Metric | Threshold | Penalty |
|---|---|---|
| max_gust_factor | ≤ 1.35 / ≤ 1.60 / > 1.60 | 0 / 15 / 35 |
| max_gust_spread | ≤ 6 / ≤ 10 / > 10 km/h | 0 / 10 / 25 |
| direction_variability | ≤ 20° / ≤ 40° / > 40° | 0 / 10 / 25 |
| speed_range | ≤ 4 / ≤ 7 / > 7 km/h | 0 / 8 / 20 |
| max_cape | ≤ 50 / ≤ 200 / > 200 J/kg | 0 / 10 / 25 |
| precipitation or showers > 0 | — | 30 |
| model dir+speed deltas | (≤25° & ≤5km/h) / (≤40° & ≤8km/h) / else | 0 / 10 / 25 |
| secondary_model_unavailable | — | 10 |
| abs(pressure_tendency_3h) | ≤ 1.5 / ≤ 2.5 / > 2.5 hPa | 0 / 5 / 15 |

After penalties: `score = max(0, min(100, score))`.

---

## 6. Labels

```
85–100  excellent
70–84   good
55–69   marginal
 0–54   poor
```

The label is included in `output_dict["label"]` for display and reason
generation. It is **not** used for boosting — the raw 0–100 sub-score is
returned directly as the first element of `(sub_score, output_dict)` from
`score_window`.

---

## 7. Reasons (machine-readable, snake_case)

```
low_gust_factor, high_gust_factor, very_gusty
stable_direction, shifting_direction, very_shifty
low_speed_range, high_speed_range
low_cape, moderate_cape, high_cape
model_agreement_good, model_disagreement, secondary_model_unavailable
pressure_stable, pressure_unstable
precipitation_risk, showers_risk
cape_unavailable, pressure_unavailable
missing_required_wind_data
```

Emit one reason per evaluated metric (the worst tier reached). Cap total
reasons at ~6 to keep delivery output readable.

---

## 8. Missing data rules

### Required (from primary model)

If `wind_speed`, `wind_direction`, or `wind_gusts` is missing for any hour
in the window from the primary model, return:

```python
(None, {"score": None, "label": "unavailable",
        "reasons": ["missing_required_wind_data"]})
```

The `None` sub-score opts the plugin out of the weighted mean; the
composite score is computed from the remaining signals (wind_speed,
wind_duration, other plugins) renormalized over their weights.

### Optional

Missing optional data → skip that penalty + emit the corresponding
`*_unavailable` reason. Optional data: `cape`, `showers`, `pressure_msl`,
secondary model.

### Primary model not in `contributing_models`

If the configured `primary_model` did not contribute to this window
(e.g. it disagreed and was filtered out by `models_agree`), fall back to
`contributing_models[0]` and add reason `primary_model_substituted`.

---

## 9. Helpers and reuse

- `angular_distance` and `vector_average_direction` already exist in
  [evaluation.py](../src/parames/evaluation.py#L35) — import, do not
  re-implement.
- `LocationConfig` is in [common.py](../src/parames/common.py); the plugin
  does not need its own location field (it always uses
  `profile.location` — passed in via `prefetch`'s `client` invocation in
  the same way Bise uses its configured locations).

> **Note:** `prefetch` currently receives `client` and `models` but not the
> alert location. Bise sidesteps this by carrying its own location config.
> For laminar, the cleanest fix is to add `location` to the prefetch
> signature on the protocol, since multiple future plugins will likely want
> the alert location. Alternative (lower-impact): accept a `location` field
> on `LaminarPluginConfig` defaulting to a copy of the alert location, set
> by config validation. **Decision pending — flag at implementation time.**

---

## 10. Integration point

The CLI runner already calls `evaluate(profile)` →
`build_candidate_windows` → `score_window(..., plugins=plugins)`. No runner
changes needed for laminar:

- Add `LaminarPluginConfig` to the discriminated `PluginConfig` union.
- Register `LaminarPlugin` via `@register_plugin`.
- Re-export from `plugins/__init__.py`.
- Append a `- type: laminar` block to the alert profile in `config/default.yaml`.
- Add `laminar: 1.0` under `scoring.weights.plugins` in `config/default.yaml`
  so the aggregator picks up the weight from global config.

The `plugin_outputs["laminar"]` dict flows through `CandidateWindow` into
delivery (console + telegram) and persistence (`pyodmongo` MongoDB store)
without any further code changes — both already serialize
`plugin_outputs` generically.

### Delivery surfacing (recommended, not required for v1)

Console and Telegram channels currently render Bise via
`plugin_outputs["bise"]["gradient_hpa"]`. To surface laminar in the same
output, add a one-line render rule:

```
Laminar: good (82) — low_gust_factor, stable_direction, low_cape
```

This is a [delivery_*.py](../src/parames/delivery/) change, not a plugin
change.

---

## 11. Testing strategy

Mirror [tests/unit/test_plugins_bise.py](../tests/unit/test_plugins_bise.py).

| Test area | What to verify |
|---|---|
| **Gust factor scoring** | Each tier (≤1.35 / ≤1.60 / >1.60) yields the right penalty + reason. |
| **Direction stability** | Stable, shifty, and wrap-through-north windows score correctly via vector mean. |
| **Speed stability** | Range thresholds; gust range tracked but not in penalty. |
| **CAPE** | Penalty tiers + missing-CAPE → penalty skipped + `cape_unavailable`. |
| **Precipitation / showers** | Any > 0 → 30 penalty + reason. `showers` missing alone is OK. |
| **Model agreement** | Pairwise deltas at percentiles; secondary missing → +10 penalty + reason. |
| **Pressure tendency** | 3h tendency normal case; window near horizon end uses fallback. |
| **Label mapping** | Score boundaries (54/55/69/70/84/85) yield the correct label in output dict. |
| **Sub-score pass-through** | `score_window` returns the raw 0–100 float as first element, not a clamped integer. |
| **Missing required wind data** | Returns `(None, unavailable_dict)` and does not raise. |
| **Disabled plugin** | `enabled=False` → `enabled` property false; `evaluate` skips it. |
| **Primary model substitution** | Config primary not in `contributing_models` → falls back + reason. |
| **Config validation** | Discriminator routes `type: laminar`; unknown fields rejected (`extra="forbid"` from `PluginConfigBase`). |

All tests construct `LaminarPrefetched` in-memory (no network).

For integration coverage: extend the existing Open-Meteo snapshot fixture
under [tests/fixtures/open_meteo](../tests/fixtures/open_meteo) so the
plugin runs against a captured response. Re-capture with:

```
PARAMES_DEV_MODE=true uv run python scripts/capture_open_meteo_snapshot.py laminar_zurich
```

---

## 12. Implementation checklist

1. Create `src/parames/plugins/laminar.py` with config, prefetched type,
   plugin class (`@register_plugin`).
2. Extend `PluginConfig` discriminated union in `plugins/schemas.py`.
3. Re-export from `plugins/__init__.py`.
4. Resolve the `prefetch(location=...)` design question (§9 note) — either
   add `location` to the protocol or carry it on the config.
5. Unit tests under `tests/unit/test_plugins_laminar.py`.
6. (Optional) Delivery one-liner in `delivery_cli.py` and
   `delivery_telegram.py`.
7. Add `- type: laminar` block to the alert profile in `config/default.yaml`.
8. Add `laminar: 1.0` to `scoring.weights.plugins` in `config/default.yaml`.
9. Capture an Open-Meteo snapshot covering gust + CAPE for replay tests.

---

## 13. Out of scope for v1

- Tuning constants against historical real-world sessions (do this after
  collecting forecast-vs-actual data; the plugin is a heuristic by design).
- Boundary-layer-height and cloud-cover signals (kept on the wishlist but
  not fetched in v1).
- Per-hour laminar scoring (v1 is window-level only).
- Webapp UI for laminar (the data is persisted and exposed via the existing
  `plugin_outputs` field — UI is a separate task).
