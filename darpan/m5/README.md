# M5 — Stress Score Engine

M5 converts M3's complaint facts into explainable 0–100 stress scores.

## Run

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m5\run.py
```

## Outputs

- `outputs/stress_scores.csv`
- `outputs/stress_scores.sqlite`
- `outputs/m5_summary.json`

## Sub-scores

| Component | Weight | Implementation |
|---|---:|---|
| Complaint intensity | 25% | Unavailable until `bank_financials` contains branch/deposit data |
| Trend velocity | 20% | Latest-year YoY complaint growth, peer-ranked |
| Resolution quality | 20% | 100 × (1 − latest disposal rate) |
| Award severity | 20% | Percentile rank of latest award amount inside bank-type peer group |
| Concentration risk | 15% | Normalized HHI over complaint categories |

## Missing-data policy

A missing component is excluded and the remaining weights are renormalized. M5 never substitutes guessed financial data or invented maintainability figures.

## Confidence

- High: 4–5 available components
- Medium: 2–3 available components
- Low: 0–1 available components

Every row contains the latest scoring year and a text evidence string for M6/M7/M8.

## Verified current result

- 8 banks scored
- 2 medium-confidence scores
- 6 low-confidence scores
- Complaint intensity unavailable: `bank_financials` is empty
- Resolution quality unavailable: M3 disposal values are largely not populated
- Award severity unavailable without at least two peer observations
- Trend and concentration are the only reproducible components for some banks

M5 does not fabricate scores for unsupported sub-components.
