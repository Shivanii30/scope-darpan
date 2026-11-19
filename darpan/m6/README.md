# M6 — Anomaly Detection Engine

M6 generates explainable complaint-volume anomalies from M3/M5 data.

## Run

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m6\run.py
```

## Outputs

- `outputs/anomalies.csv`
- `outputs/anomalies.sqlite`
- `outputs/m6_summary.json`

## Implemented methods

1. `rolling_z_score`: latest annual bank total versus prior annual mean
2. `mean_shift_change_point`: recent two-year mean versus earlier mean
3. `rolling_z_score_category`: latest category volume versus prior category mean

## Thresholds

- `low`: absolute z below 2
- `medium`: absolute z at least 2
- `high`: absolute z at least 3

M6 does not report isolation-forest or STL results until the data and dependencies support an interpretable implementation.

## Output fields

Each anomaly contains bank, year, category, method, z-score, baseline mean, observed value, severity, reason, and source context.

## Verified current result

- 3 anomalies detected
- 2 medium-severity rolling z-score/change-point events
- 1 high-severity SBI volume decrease
- All records pass schema and severity validation

No category-level z-score anomaly was emitted because category coverage in M3 is sparse. STL, ruptures, and isolation-forest layers remain intentionally unimplemented until enough annual/category evidence exists.
