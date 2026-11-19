# M4 — Orchestration & Pipeline Management

M4 runs the DARPAN pipeline with dependency checks, rerun granularity, output gates, logs, and failure alerts.

## Run the full pipeline

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m4\pipeline.py
```

## Rerun one stage

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m4\pipeline.py --stage m1
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m4\pipeline.py --stage m3
```

## Resume from a stage

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m4\pipeline.py --from-stage m2
```

## Output

- `outputs/latest.json` — latest run manifest
- `outputs/runs/<timestamp>/manifest.json` — full run manifest
- `outputs/runs/<timestamp>/m0.stdout.log`
- `outputs/runs/<timestamp>/m1.stderr.log`
- `outputs/runs/<timestamp>/failure_alert.txt`

## Gates

- M0: inventory, drift log, and strategy map exist
- M1: all spot checks pass
- M2: `validation.json` reports `ok: true`
- M3: database summary validation passes

M4 stops immediately on a blocked preflight, nonzero exit, timeout, or artifact gate failure.
