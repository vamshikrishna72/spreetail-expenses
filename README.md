# Spreetail Shared Expenses App

A small shared-expenses app for the Spreetail assignment. It imports the provided `expenses_export.csv` without manual edits, detects messy data, records an import report, calculates balances, and suggests who should pay whom.

## Features

- Login module with demo users.
- Relational SQLite database.
- Group, member, membership-window, expense, split, settlement, import-run, and anomaly tables.
- CSV import through the app.
- Import report generated as Markdown and JSON.
- Individual balance summary.
- Suggested simplified settlements.
- Expense trace page showing which expenses make up balances.

## Demo Login

- Username: `admin`
- Password: `demo123`

Other demo users: `aisha`, `rohan`, `priya`, `meera`, `sam`, all with password `demo123`.

## Setup

Requires Python 3.11+.

```bash
python app.py
```

Open:

```text
http://127.0.0.1:8000
```

Run the importer from the command line:

```bash
python app.py import
```

Run tests:

```bash
python tests.py
```

## Deployment

This app has no third-party dependencies. On Render/Railway/Fly, set the start command to:

```bash
python app.py
```

The app reads `PORT` from the environment. Set `SECRET_KEY` in production.

## AI Used

I used Codex/ChatGPT as a development collaborator for planning, anomaly review, implementation, documentation, and debugging. I remained responsible for validating the importer behavior, tests, and final decisions. Details are in `AI_USAGE.md`.

