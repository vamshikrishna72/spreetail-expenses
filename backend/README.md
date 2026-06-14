# LedgerLens Backend - Spreetail Shared Expenses

This repository contains the backend engine for **LedgerLens**, an explainable shared-expenses cleanup web application. It handles user authentication, SQLite database operations, CSV import, anomaly detection, currency conversion, complex split calculations, and settlement logging.

## Core Components
- **HTTP Server**: Built using Python's standard `http.server.BaseHTTPRequestHandler` (zero external dependencies).
- **Database**: Relational SQLite database with schema configurations (`groups`, `members`, `memberships`, `expenses`, `splits`, `settlements`, `import_runs`, `anomalies`).
- **CSV Importer**: Clean imports with data sanitization, currency translation (USD to INR), duplicate detection, and anomaly logging.
- **Test Suite**: Integration tests in `tests.py` testing database updates, dynamic percentage splits, settlements, and toggles.

## Prerequisites
- Python 3.11+
- SQLite3

## Running Locally
1. Run the database initialization and startup:
   ```bash
   python app.py
   ```
2. Run the importer from the command line:
   ```bash
   python app.py import
   ```
3. Run the integration tests:
   ```bash
   python tests.py
   ```

## Production Deployment
Set standard environment variables:
- `PORT`: Port number (defaults to `8000`).
- `SECRET_KEY`: String value used to sign session cookies.

The startup command is simply:
```bash
python app.py
```
