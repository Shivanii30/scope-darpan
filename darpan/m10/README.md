# M10 — Deployment Operations

M10 coordinates the scheduled M0-M7 refresh, captures run metrics, checks source/schema drift, validates deployment outputs, and optionally sends failure/drift alerts.

## Run once

```powershell
docker compose --profile jobs run --rm pipeline
```

The job runs M0, checks drift, then gates M1-M3 and runs M5-M7. It writes:

- `outputs/latest.json` — final status, duration, per-stage exit codes, drift and acceptance results
- `outputs/acceptance.json` — individual M1-M7/database/API checks
- `outputs/drift_report.json` — source and parser-schema differences from the accepted baseline
- `outputs/runs/<run_id>/` — per-stage stdout/stderr logs
- `state/source_schema_baseline.json` — last accepted source/schema inventory
- `outputs/scheduler_heartbeat.json` — scheduler liveness and most recent job status

## Schedule

Set in `.env` (copy from `.env.example`; `.env` is Git-ignored):

- `DARPAN_PIPELINE_SCHEDULE=monthly` or `quarterly`
- `DARPAN_SCHEDULE_HOUR_UTC=3`
- `DARPAN_RUN_ON_START=false`

Start the scheduler profile:

```powershell
docker compose --profile scheduler up -d scheduler
```

The schedule runs on the first day of the selected month/quarter at the configured UTC hour. Use `DARPAN_RUN_ON_START=true` to trigger a refresh when the scheduler container starts.

## Drift policy

`DARPAN_DRIFT_POLICY=block` is the default. Added/removed PDFs and parser, era, or text-layer changes stop the pipeline before M1. Changed file hashes/page counts are recorded as warnings. Review `outputs/drift_report.json`, then explicitly accept a reviewed change:

```powershell
docker compose --profile jobs run --rm pipeline python darpan/m10/run_pipeline.py --accept-drift
```

The baseline advances only if every downstream stage and acceptance check passes. Set the policy to `warn` only when intentionally allowing unreviewed drift.

## Monitoring and alerts

- API, dashboard, and scheduler have container healthchecks.
- Pipeline duration, stage durations, exit codes, PDF count, drift, and acceptance results are stored in JSON.
- Put the webhook URL in `secrets/alert_webhook_url.txt` (Git-ignored) or use the deployment platform's secret-file mechanism. Compose mounts it read-only at `/run/secrets/alert_webhook_url`; the value is never written to logs or reports.
- Run acceptance checks without rerunning the pipeline:

```powershell
docker compose exec -T scheduler python -m darpan.m10.acceptance
```

Do not commit `.env`; keep production webhook URLs in the deployment platform's secret manager.
