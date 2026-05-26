# Bise Plugin

## Purpose

The Bise plugin is a corroboration signal based on the east-minus-west mean sea
level pressure gradient across configured reference locations. It does not gate
wind hours directly. Instead it contributes a positive subscore only when the
pressure pattern supports a Bise setup.

When the gradient is weak, incomplete, or unavailable, the plugin opts out with
`sub_score = None`, so the weighted composite is renormalized over the
remaining signals.

## Integration

Bise is a registered evaluation plugin with:

- plugin type: `bise`
- config model: `BisePluginConfig`
- prefetched cache type: `BisePrefetched`
- result type: `PluginScoringResult`

The config participates in the discriminated `PluginConfig` union and is also
used directly in persisted alert definitions.

## Configuration

```yaml
plugins:
  - type: bise
    enabled: true
    east_minus_west_pressure_hpa_min: 1.5
    pressure_reference_west:
      name: geneva
      latitude: 46.204
      longitude: 6.143
    pressure_reference_east:
      name: guettingen
      latitude: 47.604
      longitude: 9.287
```

Fields:

- `east_minus_west_pressure_hpa_min`: minimum corroborating gradient
- `pressure_reference_west`: west-side pressure reference location
- `pressure_reference_east`: east-side pressure reference location

## Prefetch

For every model in the alert profile, Bise fetches `pressure_msl` for both
reference locations.

The prefetched cache is stored as:

```python
PressureByModel = dict[str, dict[datetime, HourForecast]]

class BisePrefetched:
    west: PressureByModel
    east: PressureByModel
```

The plugin does not use the alert location for scoring and ignores the
`location` argument passed into `prefetch`.

## Window Scoring

For each timestamp in the candidate window, Bise evaluates only the models that
contributed to that window.

### Per-Model Gradient

For a given timestamp and model:

```text
gradient_hpa = east.pressure_msl - west.pressure_msl
```

Only models with both east and west `pressure_msl` values present for that
timestamp are included.

### Per-Timestamp Mean

For each window hour:

- if at least one contributing model has complete east and west pressure, Bise records the mean gradient for that timestamp
- otherwise that timestamp is marked missing for completeness purposes

### Completeness Gate

Bise requires complete gradient coverage for the entire window. If any window
timestamp has no usable pressure gradient from the contributing models, the
plugin opts out entirely.

On opt-out due to incompleteness:

- `sub_score = None`
- `output = {}`
- the report contains a failing `data_completeness` rule

Because the compact output is empty, `CandidateWindow.plugin_outputs` will not
contain a `bise` entry for that window.

### Gradient Thresholds

If the window is complete, Bise averages the per-timestamp means:

```text
avg_gradient_hpa = average(mean_gradient_hpa over window)
```

Scoring:

| Condition | `sub_score` | Outcome |
|---|---|---|
| `avg_gradient_hpa >= 3.0` | `100.0` | strong corroboration |
| `avg_gradient_hpa >= east_minus_west_pressure_hpa_min` and `< 3.0` | `75.0` | moderate corroboration |
| `avg_gradient_hpa < east_minus_west_pressure_hpa_min` | `None` | opt out |

Below-threshold gradients do not produce a penalty. They simply remove Bise
from the weighted mean for that window.

## Compact Output

When Bise participates positively, it writes:

```json
{
  "gradient_hpa": 2.4
}
```

This value is the mean east-minus-west gradient across the window after
averaging per-timestamp means.

## Report Output

Bise emits a `PluginReport` regardless of whether it contributed a subscore.

### Summary

Examples:

- `Avg gradient 3.10 hPa — pass`
- `Avg gradient 2.00 hPa — warn`
- incompleteness case: no summary text, but a failing completeness rule

### Inputs

The report captures:

- `contributing_models`
- `west_location`
- `east_location`

### Metrics

When the window is complete, the report contains:

- `avg_gradient_hpa`
- `min_gradient_hpa`
- `max_gradient_hpa`

### Hourly Trace

Each window hour produces an entry shaped like:

```json
{
  "time": "2026-04-29T12:00:00+02:00",
  "per_model_gradient_hpa": {
    "icon_d2": 2.1,
    "ecmwf_ifs": 2.4
  },
  "mean_gradient_hpa": 2.25
}
```

If no model had usable pressure data at that timestamp, `per_model_gradient_hpa`
is empty and `mean_gradient_hpa` is `null`.

### Rules

Bise currently emits these rule types:

- `data_completeness`
- `gradient_threshold`

`gradient_threshold` is graded as:

- `pass` for `>= 3.0`
- `warn` for `>= east_minus_west_pressure_hpa_min` and `< 3.0`
- `fail` for `< east_minus_west_pressure_hpa_min`

## Aggregation and Delivery

Bise's composite weight is looked up from `scoring.weights.plugins.bise`. The
shipped default config sets that weight to `0.7`.

Console and Telegram delivery both render the compact gradient when present and
show `unavailable` otherwise:

```text
Bise gradient: +2.4 hPa east-west
```

If Bise opts out due to low gradient or missing data, the delivery layer still
knows the plugin was configured because `window.subscores` contains `bise: None`.
