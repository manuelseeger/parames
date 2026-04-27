# parames

Paragliding wind alert proof of concept for Zurich Bise ground handling.

## Usage

Install dependencies and run the CLI:

```powershell
uv sync
uv run parames
```

Override the config path when needed:

```powershell
uv run parames --config config/default.yaml
```

Run tests:

```powershell
uv run pytest -m "not integration"
uv run pytest -m integration
```

Capture a live Open-Meteo snapshot for a future replay test:

```powershell
uv run python scripts/capture_open_meteo_snapshot.py my_snapshot_name
```

Override the alert profile or config when needed:

```powershell
uv run python scripts/capture_open_meteo_snapshot.py my_snapshot_name --alert zurich_bise --config config/default.yaml
```
