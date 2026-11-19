# M8 — API Layer

M8 exposes M3/M5/M6/M7 through FastAPI.

## Run

```powershell
cd c:\Users\kshiv\Downloads\banking\final\darpan\m8
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe run.py
```

Open:

- API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/health>

## Endpoints

- `GET /banks`
- `GET /banks/{id}/stress`
- `GET /banks/{id}/anomalies`
- `GET /banks/{id}?` — use `/banks/{id}/stress` / `/anomalies`
- `GET /analytics/peer-compare`
- `GET /briefs/{id}`
- `GET /briefs/{id}/download`
- `GET /analytics/trends/{id}`

## Filters

- `/banks?bank_type=PSU`
- `/banks?stress_tier=low`
- `/analytics/peer-compare?bank_type=PSU`

The API is read-only and uses M3/M5/M6/M7 artifacts without recomputation.
