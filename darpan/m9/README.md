# M9 — Frontend Dashboard

M9 is a Streamlit v1 dashboard connected to the live M8 FastAPI service.

## Run

Start M8 first:

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m8\run.py
```

Start M9:

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m9\run.py
```

Open:

- Dashboard: <http://127.0.0.1:8501>
- API: <http://127.0.0.1:8000>
- API docs: <http://127.0.0.1:8000/docs>

## Views

- Bank explorer with bank-type and stress-tier filters
- Stress score and component chart
- Annual complaint trend chart
- Peer comparison chart
- Anomaly timeline
- Markdown policy brief viewer and download

## Data rule

M9 does not recompute scores or anomaly flags. It consumes M8 endpoints only and clearly shows unavailable M5 components.
