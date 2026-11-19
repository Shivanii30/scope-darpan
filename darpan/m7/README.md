# M7 — Policy Brief Generator

M7 creates a fixed six-section policy brief for every M5-scored bank using only precomputed M5/M6 values.

## Run

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m7\run.py
```

## Outputs

- `outputs/briefs.json`
- `outputs/<bank_id>.md` for each bank
- `outputs/m7_summary.json`

## Fixed sections

1. Executive Summary
2. Trend Analysis
3. Stress Score Rationale
4. Peer Positioning
5. Anomalies Flagged
6. Data Provenance

## Safety rule

M7 does not use an LLM, retrieve PDFs, calculate scores, or invent figures. Missing M5 sub-components remain explicitly unavailable.
