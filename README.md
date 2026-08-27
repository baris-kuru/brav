# brav

brav is a local cafe-management assistant around your existing OpenClaw and Fireworks setup on this laptop.

## What it does

- ingests PDF batches from a browser UI
- stores normalized receipts and line items in SQLite for later analysis
- tracks stock levels, suppliers, reorder pressure, daypart demand, weather, holiday/weekend signals and staffing forecasts
- answers cafe-management questions as a manager twin using the current cafe state
- exposes the same database to OpenClaw through a plugin tool

## Project layout

- `backend/`: FastAPI app, receipt extraction pipeline, analytics, SQLite access
- `static/`: local operations cockpit
- `openclaw-cafe-agent/`: OpenClaw plugin that talks to the backend
- `data/`: runtime SQLite database and uploaded PDFs

## Setup

1. Create a Python environment and install dependencies.
2. Start the backend:

```bash
./scripts/start.sh
```

3. Open [http://127.0.0.1:8010](http://127.0.0.1:8010)
4. Press `Load cafe data` to seed the dashboard with stock, staffing, calendar and manager-priority data.
5. Install the OpenClaw plugin from `openclaw-cafe-agent/` using your normal local OpenClaw path-plugin workflow.

## AI configuration

The backend looks for `FIREWORKS_API_KEY` and `FIREWORKS_MODEL` in:

- this repo's `.env`
- the sibling `../HomeAssistant/.env`
- current shell environment

That means it can reuse the Fireworks/OpenClaw preference already present on this laptop. If no AI key is available, the app still works with heuristic parsing and basic summaries.

## Useful API endpoints

- `GET /api/dashboard`
- `GET /api/operations`
- `POST /api/data/seed`
- `POST /api/manager/ask`
- `GET /api/receipts`
- `POST /api/receipts/ingest`
- `POST /api/analysis/ask`

## Product Narrative

brav is shaped around a cafe manager digital twin. It combines operational signals that a real manager would watch during a shift:

- stock health and reorder urgency
- expected demand by time of day
- recommended staff vs scheduled staff
- weather, holiday and weekend context
- receipt and supplier spending context
- open action priorities

The initial dataset is intentionally small and readable, so it can be reviewed quickly and replaced with real POS, inventory, staff rota and weather feeds later.

## Notes

- The extraction flow groups PDF text into windows and asks the model to return multiple receipts when a file contains more than one.
- For very noisy scans, you can later swap the text extraction stage to OCR or Docling without changing the database or UI shape.
