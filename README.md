# CS2 Demo Analytics

A local analytics tool for Counter-Strike 2 `.dem` files built with FastAPI, pandas, SQLite, and vanilla JS.

## Project Tree

```text
CS2DemoAnalytics/
├── cs2_demo_analytics/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── demo_parser.py
│   ├── metrics.py
│   ├── models.py
│   ├── schemas.py
│   └── service.py
├── data/
│   ├── cs2_analytics.db (created at runtime)
│   └── uploads/ (created at runtime)
├── static/
│   ├── app.js
│   └── styles.css
├── templates/
│   └── index.html
├── main.py
├── requirements.txt
└── README.md
```

## Features

- Demo upload (`.dem`) and processing pipeline
- Event extraction (kills, damage, shots)
- Core metrics: K/D, ADR, accuracy, damage, headshots, etc.
- Round metrics: kills/damage/survival time per round
- Custom metrics:
  - Damage Timing Metric
  - Kill Reaction Time
  - Aim Consistency Score (0-100)
  - Aim Efficiency Score (0-100)
  - Engagement stats for opening duels/trades/clutch indicators
- SQLite persistence with relational tables: players, matches, rounds, events, metrics
- Dashboard with tables and Chart.js charts

## Installation

1. Create and activate a virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Run Backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Open Dashboard

- Open `http://localhost:8000` in your browser.

## Upload Demo

1. Click **Choose File** and select a `.dem` file.
2. Click **Analyze Demo**.
3. Review overview cards, custom metrics table, round stats table, and charts.

## Notes on Demo Parsing

- The app tries `demoparser2` first for real event parsing.
- If parser integration fails (missing parser support or unsupported file), it falls back to deterministic synthetic events derived from file content so the full pipeline remains locally testable.
