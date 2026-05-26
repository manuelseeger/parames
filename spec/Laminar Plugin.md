# Laminar Plugin

## Purpose

The Laminar plugin is a quality signal for already-accepted candidate windows.
It does not decide whether wind direction or wind speed is suitable. Instead it
scores how smooth, stable, dry-looking, and model-consistent the accepted
window appears.

It returns a raw `sub_score` in `[0, 100]` when the primary model has complete
required wind data for the full window. Lower scores drag the weighted
composite down proportionally. It only opts out with `sub_score = None` when
required wind data is missing.

## Integration

Laminar is a registered evaluation plugin with:

- plugin type: `laminar`
- config model: `LaminarPluginConfig`
- prefetched cache type: `LaminarPrefetched`
- result type: `PluginScoringResult`

The config is part of the discriminated `PluginConfig` union and is re-exported
from `parames.plugins`.

## Configuration

```yaml
plugins:
  - type: laminar
    enabled: true
    primary_model: null
    secondary_model: null
    wind_level_m: 10

    gust_factor:
      good_max: 1.35
      marginal_max: 1.60

    gust_spread_kmh:
      good_max: 6.0
      marginal_max: 10.0

    direction_variability_deg:
      good_max: 20.0
      marginal_max: 40.0

    speed_range_kmh:
      good_max: 4.0
      marginal_max: 7.0

    cape_j_kg:
      good_max: 50.0
      marginal_max: 200.0

    model_agreement:
      direction_good_max_deg: 25.0
      direction_marginal_max_deg: 40.0
      speed_good_max_kmh: 5.0
      speed_marginal_max_kmh: 8.0

    pressure_tendency_3h_hpa:
      good_max_abs: 1.5
      marginal_max_abs: 2.5

    precipitation:
      max_precip_mm_h: 0.0
      max_showers_mm_h: 0.0
```

### Notes

- `wind_level_m` is part of the plugin config. It must match the alert profile's wind level for gust variables to line up with the main wind forecast.
- `primary_model` is used only if it is present in `contributing_models`.
- `secondary_model` is used if it exists in the prefetched cache. Otherwise the plugin falls back to the first contributing secondary model present in the cache.

## Prefetch

Laminar prefetches the full alert-location horizon for every model in the alert
profile using:

- `wind_speed_{wind_level_m}m`
- `wind_direction_{wind_level_m}m`
- `wind_gusts_{wind_level_m}m`
- `precipitation`
- `showers`
- `cape`
- `pressure_msl`

The cache is stored as:

```python
class LaminarPrefetched:
    data: dict[str, dict[datetime, HourForecast]]
```

Laminar re-fetches wind, precipitation, and pressure for its own cache instead
of reusing the core forecast snapshot.

## Model Resolution

### Primary Model

Primary model selection is resolved at score time:

1. Use `config.primary_model` if it is in `contributing_models`.
2. If `config.primary_model` is set but absent from `contributing_models`, use `contributing_models[0]` and add the reason `primary_model_substituted`.
3. Otherwise use `contributing_models[0]`.

### Secondary Model

Secondary model selection is resolved at score time:

1. Use `config.secondary_model` if it exists in the prefetched cache.
2. Otherwise scan `contributing_models[1:]` and pick the first model present in the prefetched cache.
3. If none is found, treat the secondary model as unavailable.

Both selections are also recorded in the plugin report rules as informational
entries.

## Required Data Gate

Laminar requires the primary model to have, for every timestamp in the window:

- `wind_speed`
- `wind_direction`
- `wind_gusts`

If any of those fields are missing for any window hour, Laminar returns:

```json
{
  "sub_score": null,
  "output": {
    "score": null,
    "label": "unavailable",
    "reasons": ["missing_required_wind_data"]
  }
}
```

In that case the plugin also emits a report with a failing `data_gate` rule.

## Metrics and Scoring

Laminar starts from `100.0` and subtracts penalties. The final raw score is
clamped to `[0.0, 100.0]`. The compact output rounds the score to an integer,
but the returned `sub_score` remains a float.

### Gust Factor

Per hour:

```text
gust_factor = wind_gusts / max(wind_speed, 1.0)
gust_spread_kmh = wind_gusts - wind_speed
```

Window metrics:

- `avg_gust_factor`
- `max_gust_factor`
- `avg_gust_spread_kmh`
- `max_gust_spread_kmh`

Penalties:

| Metric | Tier | Penalty | Reason |
|---|---|---|---|
| `max_gust_factor <= good_max` | good | `0` | `low_gust_factor` |
| `good_max < max_gust_factor <= marginal_max` | warn | `10` | `high_gust_factor` |
| `max_gust_factor > marginal_max` | fail | `35` | `very_gusty` |
| `max_gust_spread_kmh <= good_max` | good | `0` | none |
| `good_max < max_gust_spread_kmh <= marginal_max` | warn | `7` | none |
| `max_gust_spread_kmh > marginal_max` | fail | `25` | none |

Only gust factor contributes a user-facing reason. Gust spread is recorded in
the report and metrics but does not add a reason string.

### Direction Stability

Laminar uses vector-average direction and circular angular distance:

```text
mean_dir = vector_average_direction(window_directions)
direction_variability_deg = max(angular_distance(direction, mean_dir))
```

Penalties:

| Tier | Condition | Penalty | Reason |
|---|---|---|---|
| good | `<= 20` | `0` | `stable_direction` |
| warn | `> 20` and `<= 40` | `7` | `shifting_direction` |
| fail | `> 40` | `25` | `very_shifty` |

### Speed Stability

Window metrics:

```text
speed_range_kmh = max(wind_speed) - min(wind_speed)
gust_range_kmh = max(wind_gusts) - min(wind_gusts)
```

`gust_range_kmh` is computed internally but is not surfaced in the compact
metrics output.

Penalties:

| Tier | Condition | Penalty | Reason |
|---|---|---|---|
| good | `<= 4` | `0` | `low_speed_range` |
| warn | `> 4` and `<= 7` | `5` | `high_speed_range` |
| fail | `> 7` | `20` | `high_speed_range` |

### CAPE

CAPE is treated as available only when more than half of the window hours have
`cape` values.

If CAPE is unavailable:

- no CAPE penalty is applied
- Laminar adds the reason `cape_unavailable`
- the report includes an informational `cape_availability` rule

If CAPE is available, penalties are based on `max_cape`:

| Tier | Condition | Penalty | Reason |
|---|---|---|---|
| good | `<= 50` | `0` | `low_cape` |
| warn | `> 50` and `<= 200` | `7` | `moderate_cape` |
| fail | `> 200` | `25` | `high_cape` |

### Precipitation and Showers

Window metrics:

```text
max_precipitation = max(h.precipitation or 0.0)
max_showers = max(h.showers or 0.0)
```

Penalties are applied independently:

| Metric | Condition | Penalty | Reason |
|---|---|---|---|
| precipitation | `max_precipitation > max_precip_mm_h` | `15` | `precipitation_risk` |
| showers | `max_showers > max_showers_mm_h` | `15` | `showers_risk` |

Missing showers are treated as `0.0`. There is no `showers_unavailable`
reason in the current implementation.

### Pressure Tendency

Laminar tries to measure a 3-hour pressure tendency from the primary model.

Primary calculation:

```text
pressure_tendency_3h_hpa = pressure_msl[window_start + 3h] - pressure_msl[window_start]
```

Fallback calculation when the exact `t+3h` value is unavailable:

```text
pressure_tendency_3h_hpa = (last_pressure - first_pressure) * (3 / full_prefetched_duration_hours)
```

This fallback uses the full prefetched primary-model pressure series, not just
the window span.

Behavior:

- if no primary-model pressure is present for any window hour, Laminar adds `pressure_unavailable` and records an informational rule
- if a tendency is derived, it is scored on absolute value
- if pressure exists but no tendency can be derived, no pressure reason is added and no pressure penalty is applied

Penalties when a tendency is available:

| Tier | Condition | Penalty | Reason |
|---|---|---|---|
| good | `abs(tendency) <= 1.5` | `0` | `pressure_stable` |
| warn | `> 1.5` and `<= 2.5` | `3` | `pressure_unstable` |
| fail | `> 2.5` | `15` | `pressure_unstable` |

The report rule message is `fallback_scaled` when the fallback path was used.

### Model Agreement

Model agreement compares the resolved primary and secondary models using only
wind direction and wind speed.

Per timestamp with overlapping data:

```text
dir_delta = angular_distance(primary.wind_direction, secondary.wind_direction)
speed_delta = abs(primary.wind_speed - secondary.wind_speed)
```

For windows shorter than 4 hours, Laminar scores the `max` of each delta.
For windows of 4 hours or more, it scores the 75th percentile of each delta.

Penalties:

| Tier | Condition | Penalty | Reason |
|---|---|---|---|
| good | `dir <= 25` and `speed <= 5` | `0` | `model_agreement_good` |
| warn | `dir <= 40` and `speed <= 8` | `7` | `model_disagreement` |
| fail | otherwise | `25` | `model_disagreement` |

If no secondary model can be resolved, or if there is no overlapping data
between the primary and secondary model across the window, Laminar applies a
`7` point penalty and adds `secondary_model_unavailable`.

## Label Mapping

The compact output label is derived from the raw float score before rounding:

| Score | Label |
|---|---|
| `85-100` | `excellent` |
| `70-84.999...` | `good` |
| `55-69.999...` | `marginal` |
| `< 55` | `poor` |

## Compact Output

When Laminar returns a score, `CandidateWindow.plugin_outputs["laminar"]`
contains:

```json
{
  "score": 82,
  "label": "good",
  "reasons": [
    "low_gust_factor",
    "stable_direction",
    "low_speed_range",
    "low_cape",
    "pressure_stable",
    "model_agreement_good"
  ],
  "metrics": {
    "avg_gust_factor": 1.2,
    "max_gust_spread_kmh": 4.0,
    "direction_variability_deg": 6.0,
    "speed_range_kmh": 2.0,
    "pressure_tendency_3h_hpa": 0.5,
    "max_cape": 10.0,
    "model_direction_delta_deg": 3.0,
    "model_speed_delta_kmh": 1.0
  },
  "primary_model": "icon_d2",
  "secondary_model": "ecmwf_ifs"
}
```

Notes:

- `score` is `round(sub_score)`
- `reasons` is truncated to the first six entries
- `secondary_model` may be `null`
- `max_cape`, `model_direction_delta_deg`, and `model_speed_delta_kmh` appear only when those values are available

## Report Output

Laminar also emits a `PluginReport` with:

- `summary`: `score=<rounded> label=<label>`
- `config_snapshot`: full plugin config
- `inputs`: resolved primary model, resolved secondary model, and contributing models
- `metrics`: the same aggregate metrics used in the compact output
- `rules`: ordered rule evaluations for model resolution, data gate, gusts, direction, speed range, CAPE, precipitation, showers, pressure tendency, and model agreement
- `hourly`: one row per window hour with gust metrics, primary values, optional secondary values, and optional `dir_delta` and `speed_delta`

The hourly rows are shaped like:

```json
{
  "time": "2026-04-29T12:00:00+02:00",
  "gust_factor": 1.2,
  "gust_spread_kmh": 4.0,
  "primary": {
    "wind_speed": 20.0,
    "wind_direction": 60.0,
    "wind_gusts": 24.0,
    "cape": 10.0,
    "pressure_msl": 1015.0
  },
  "secondary": {
    "wind_speed": 21.0,
    "wind_direction": 63.0,
    "wind_gusts": 25.0
  },
  "dir_delta": 3.0,
  "speed_delta": 1.0
}
```

## Current Reason Set

The current implementation can emit these compact reasons:

- `primary_model_substituted`
- `missing_required_wind_data`
- `low_gust_factor`
- `high_gust_factor`
- `very_gusty`
- `stable_direction`
- `shifting_direction`
- `very_shifty`
- `low_speed_range`
- `high_speed_range`
- `cape_unavailable`
- `low_cape`
- `moderate_cape`
- `high_cape`
- `precipitation_risk`
- `showers_risk`
- `pressure_unavailable`
- `pressure_stable`
- `pressure_unstable`
- `secondary_model_unavailable`
- `model_agreement_good`
- `model_disagreement`

## Aggregation and Delivery

Laminar's composite weight is looked up from `scoring.weights.plugins.laminar`.
The shipped default config sets that weight to `0.7`.

Console and Telegram delivery both render Laminar as a short line using the
compact output label and up to three reasons:

```text
Laminar: good (low_gust_factor, stable_direction, low_cape)
```
