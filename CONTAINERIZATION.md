# DARPAN Containers

The Docker image contains M0-M10 Python code. RBI PDFs are not included in the image; the batch pipeline mounts `Ombudsman/` read-only. Module outputs are bind-mounted so the SQLite database, JSON/CSV outputs, and logs persist in the workspace.

## Build and run

From the workspace root:

```powershell
docker compose build
```

Run the data pipeline once (or whenever source data changes):

```powershell
docker compose --profile jobs run --rm pipeline
```

Start the monthly/quarterly scheduler:

```powershell
docker compose --profile scheduler up -d scheduler
```

The scheduler runs at 03:00 UTC on the first day of each scheduled period by default. It writes its heartbeat, source drift report, acceptance report, stage logs, and latest-run metrics under `darpan/m10/outputs/`.

Then start the API and dashboard:

```powershell
docker compose up -d api dashboard
```

Open:

- Dashboard: <http://localhost:8501>
- API docs: <http://localhost:18000/docs>
- API health: <http://localhost:18000/health>

The API reads M3/M5/M6/M7 data on startup. After a later pipeline run, restart the API to reload those artifacts:

```powershell
docker compose restart api
```

Stop services:

```powershell
docker compose down
```

## Drift, monitoring, and alerts

M10 compares the current M0 inventory with the last accepted source/schema baseline before starting M1. The default `DARPAN_DRIFT_POLICY=block` stops on added/removed PDFs and changes to text-layer status, format era, parser schema, or extraction strategy. Review `darpan/m10/outputs/drift_report.json` before accepting a change:

```powershell
docker compose --profile jobs run --rm pipeline python darpan/m10/run_pipeline.py --accept-drift
```

The accepted baseline is advanced only after all downstream stages and acceptance checks pass. Use `DARPAN_DRIFT_POLICY=warn` only when intentionally allowing unreviewed drift.

Acceptance checks verify M1-M7 validation, SQLite fact/year coverage, and API health when `DARPAN_API_URL` is configured. Run them on demand:

```powershell
docker compose exec -T scheduler python -m darpan.m10.acceptance
```

Optional webhook notifications are sent on source drift and pipeline failures. Put the URL in the Git-ignored `secrets/alert_webhook_url.txt` or use the deployment platform's secret-file mechanism; Compose mounts it read-only at `/run/secrets/alert_webhook_url`. The URL is never passed in the container environment or written to logs/reports.

## Configuration

- `DARPAN_API_PORT`: host API port, default `18000` (container listens on `8000`)
- `DARPAN_WEB_PORT`: host dashboard port, default `8501`
- `DARPAN_PIPELINE_SCHEDULE`: `monthly` or `quarterly` (default `monthly`)
- `DARPAN_SCHEDULE_HOUR_UTC`: UTC hour from `0` to `23` (default `3`)
- `DARPAN_RUN_ON_START`: run immediately when scheduler starts (default `false`)
- `DARPAN_DRIFT_POLICY`: `block` or `warn` (default `block`)
- `ALERT_WEBHOOK_FILE`: secret-file path, default `./secrets/alert_webhook_url.txt`
- The dashboard uses `DARPAN_API_URL=http://api:8000` inside Compose.

The `jobs` profile runs the pipeline once and exits. The `scheduler` profile is a persistent service with a Docker healthcheck. Both invoke the same M10 orchestrator and share output/baseline volumes.

## Local development

The local M8 default remains `http://127.0.0.1:8000`; M9 also accepts `DARPAN_API_URL` for alternate API locations. M4 and M9 launchers now use the active Python interpreter rather than machine-specific Windows paths.
