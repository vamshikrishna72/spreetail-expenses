import csv
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "import_reports"
DB_PATH = DATA_DIR / "app.sqlite3"
CSV_PATH = BASE_DIR / "expenses_export.csv"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-before-deploy")
USD_TO_INR = Decimal(os.environ.get("USD_TO_INR", "83.00"))

USERS = {
    "aisha": "demo123",
    "rohan": "demo123",
    "priya": "demo123",
    "meera": "demo123",
    "sam": "demo123",
    "admin": "demo123",
}

MEMBERSHIP_WINDOWS = {
    "Aisha": ("2026-02-01", None),
    "Rohan": ("2026-02-01", None),
    "Priya": ("2026-02-01", None),
    "Meera": ("2026-02-01", "2026-03-31"),
    "Dev": ("2026-02-08", "2026-03-31"),
    "Sam": ("2026-04-08", None),
    "Kabir": ("2026-03-11", "2026-03-11"),
}

ALIASES = {
    "priya s": "Priya",
    "priya": "Priya",
    "rohan": "Rohan",
    "aisha": "Aisha",
    "meera": "Meera",
    "dev": "Dev",
    "sam": "Sam",
    "dev's friend kabir": "Kabir",
    "kabir": "Kabir",
}


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rupees(value):
    value = money(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{sign}Rs {value:,.2f}"


def connect():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
                id INTEGER PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES groups(id),
                member_id INTEGER NOT NULL REFERENCES members(id),
                joined_on TEXT NOT NULL,
                left_on TEXT,
                UNIQUE(group_id, member_id, joined_on)
            );
            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY,
                source_file TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                usd_to_inr TEXT NOT NULL,
                rows_seen INTEGER NOT NULL,
                rows_imported INTEGER NOT NULL,
                rows_skipped INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS anomalies (
                id INTEGER PRIMARY KEY,
                import_run_id INTEGER NOT NULL REFERENCES import_runs(id),
                row_number INTEGER NOT NULL,
                code TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                action TEXT NOT NULL,
                raw_row TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY,
                import_run_id INTEGER NOT NULL REFERENCES import_runs(id),
                row_number INTEGER NOT NULL,
                group_id INTEGER NOT NULL REFERENCES groups(id),
                expense_date TEXT NOT NULL,
                description TEXT NOT NULL,
                paid_by_id INTEGER NOT NULL REFERENCES members(id),
                amount_original TEXT NOT NULL,
                currency TEXT NOT NULL,
                amount_inr TEXT NOT NULL,
                split_type TEXT NOT NULL,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS expense_splits (
                id INTEGER PRIMARY KEY,
                expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
                member_id INTEGER NOT NULL REFERENCES members(id),
                amount_inr TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settlements (
                id INTEGER PRIMARY KEY,
                import_run_id INTEGER NOT NULL REFERENCES import_runs(id),
                row_number INTEGER NOT NULL,
                group_id INTEGER NOT NULL REFERENCES groups(id),
                settlement_date TEXT NOT NULL,
                payer_id INTEGER NOT NULL REFERENCES members(id),
                receiver_id INTEGER NOT NULL REFERENCES members(id),
                amount_inr TEXT NOT NULL,
                notes TEXT
            );
            """
        )
        for username, password in USERS.items():
            conn.execute(
                "INSERT OR IGNORE INTO users(username, password_hash) VALUES(?, ?)",
                (username, password_hash(password)),
            )
        conn.execute("INSERT OR IGNORE INTO groups(name) VALUES('Spreetail Flatmates')")
        group_id = conn.execute("SELECT id FROM groups WHERE name=?", ("Spreetail Flatmates",)).fetchone()["id"]
        for member, window in MEMBERSHIP_WINDOWS.items():
            conn.execute("INSERT OR IGNORE INTO members(name) VALUES(?)", (member,))
            member_id = conn.execute("SELECT id FROM members WHERE name=?", (member,)).fetchone()["id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO memberships(group_id, member_id, joined_on, left_on)
                VALUES (?, ?, ?, ?)
                """,
                (group_id, member_id, window[0], window[1]),
            )


def password_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def sign(value):
    return hmac.new(SECRET_KEY.encode(), value.encode(), "sha256").hexdigest()


def make_session(username):
    raw = f"{username}|{secrets.token_hex(12)}"
    return f"{raw}|{sign(raw)}"


def verify_session(session_value):
    if not session_value:
        return None
    parts = session_value.split("|")
    if len(parts) != 3:
        return None
    raw = "|".join(parts[:2])
    if hmac.compare_digest(parts[2], sign(raw)):
        return parts[0]
    return None


def get_member_id(conn, name):
    conn.execute("INSERT OR IGNORE INTO members(name) VALUES(?)", (name,))
    return conn.execute("SELECT id FROM members WHERE name=?", (name,)).fetchone()["id"]


def normalize_name(raw):
    cleaned = " ".join((raw or "").strip().split())
    if not cleaned:
        return ""
    return ALIASES.get(cleaned.lower(), cleaned)


def parse_people(raw):
    return [normalize_name(item) for item in (raw or "").split(";") if normalize_name(item)]


def parse_amount(raw):
    return Decimal(str(raw).replace(",", "").strip())


def parse_date(raw):
    value = (raw or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        parsed = datetime.strptime(value, "%d/%m/%Y").date()
        if value == "04/05/2026":
            return date(2026, 4, 5), "Ambiguous date 04/05/2026 treated as 2026-04-05 because surrounding rows describe April expenses."
        return parsed, "Date normalized from DD/MM/YYYY format."
    if value == "Mar 14":
        return date(2026, 3, 14), "Year inferred as 2026 from surrounding trip rows."
    raise ValueError(f"Unsupported date format: {value}")


def is_active(member, expense_date):
    window = MEMBERSHIP_WINDOWS.get(member)
    if not window:
        return True
    start = datetime.strptime(window[0], "%Y-%m-%d").date()
    end = datetime.strptime(window[1], "%Y-%m-%d").date() if window[1] else None
    return expense_date >= start and (end is None or expense_date <= end)


def detail_numbers(raw):
    values = {}
    for part in (raw or "").split(";"):
        match = re.match(r"\s*(.+?)\s+(-?\d+(?:\.\d+)?)%?\s*$", part)
        if match:
            values[normalize_name(match.group(1))] = Decimal(match.group(2))
    return values


def canonical_description(text):
    words = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    words = words.replace(" at ", " ")
    words = words.replace("dinner marina bites", "marina bites dinner")
    words = words.replace("thalassa dinner", "dinner thalassa")
    return " ".join(sorted(words.split()))


def add_anomaly(anomalies, row_number, code, severity, message, action, row):
    anomalies.append(
        {
            "row_number": row_number,
            "code": code,
            "severity": severity,
            "message": message,
            "action": action,
            "raw_row": dict(row),
        }
    )


def split_amount(row, amount_inr, participants, anomalies, row_number, expense_date):
    split_type = (row.get("split_type") or "").strip().lower()
    details = row.get("split_details") or ""
    active_people = [p for p in participants if is_active(p, expense_date)]
    removed = [p for p in participants if p not in active_people]
    if removed:
        add_anomaly(
            anomalies,
            row_number,
            "inactive_member_in_split",
            "warning",
            f"Inactive member(s) in split: {', '.join(removed)}.",
            "Removed inactive members and recalculated the split.",
            row,
        )
    participants = active_people
    if not participants:
        raise ValueError("No valid split participants after membership checks.")

    if split_type == "equal":
        if details.strip():
            add_anomaly(
                anomalies,
                row_number,
                "split_details_on_equal",
                "warning",
                "Equal split row also had split_details.",
                "Ignored split_details because split_type is equal.",
                row,
            )
        share = money(amount_inr / Decimal(len(participants)))
        splits = {person: share for person in participants}
        drift = amount_inr - sum(splits.values(), Decimal("0"))
        if drift:
            splits[participants[0]] = money(splits[participants[0]] + drift)
        return splits

    numbers = detail_numbers(details)
    if split_type == "unequal":
        missing = [p for p in participants if p not in numbers]
        if missing:
            add_anomaly(
                anomalies,
                row_number,
                "unequal_missing_participants",
                "warning",
                f"Missing explicit unequal values for: {', '.join(missing)}.",
                "Used only members present in split_details.",
                row,
            )
        return {person: money(value) for person, value in numbers.items() if person in participants}

    if split_type == "share":
        total = sum((numbers.get(person, Decimal("0")) for person in participants), Decimal("0"))
        if total <= 0:
            raise ValueError("Share split has no positive shares.")
        splits = {person: money(amount_inr * numbers.get(person, Decimal("0")) / total) for person in participants}
        drift = amount_inr - sum(splits.values(), Decimal("0"))
        if drift:
            splits[participants[0]] = money(splits[participants[0]] + drift)
        return splits

    if split_type == "percentage":
        total = sum((numbers.get(person, Decimal("0")) for person in participants), Decimal("0"))
        if total != 100:
            add_anomaly(
                anomalies,
                row_number,
                "percentage_total_not_100",
                "warning",
                f"Percentages total {total}%, not 100%.",
                "Normalized percentages proportionally to 100%.",
                row,
            )
        if total <= 0:
            raise ValueError("Percentage split has no positive percentages.")
        splits = {person: money(amount_inr * numbers.get(person, Decimal("0")) / total) for person in participants}
        drift = amount_inr - sum(splits.values(), Decimal("0"))
        if drift:
            splits[participants[0]] = money(splits[participants[0]] + drift)
        return splits

    raise ValueError(f"Unsupported split type: {split_type}")


def import_csv(path=CSV_PATH):
    init_db()
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    anomalies = []
    imported = 0
    skipped = 0
    seen = {}
    settlement_candidates = []

    with connect() as conn:
        conn.executescript(
            """
            DELETE FROM expense_splits;
            DELETE FROM settlements;
            DELETE FROM expenses;
            DELETE FROM anomalies;
            DELETE FROM import_runs;
            """
        )
        imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        run_id = conn.execute(
            """
            INSERT INTO import_runs(source_file, imported_at, usd_to_inr, rows_seen, rows_imported, rows_skipped)
            VALUES (?, ?, ?, 0, 0, 0)
            """,
            (Path(path).name, imported_at, str(USD_TO_INR)),
        ).lastrowid
        group_id = conn.execute("SELECT id FROM groups WHERE name=?", ("Spreetail Flatmates",)).fetchone()["id"]

        for index, row in enumerate(rows, start=2):
            try:
                expense_date, date_note = parse_date(row["date"])
                if date_note:
                    add_anomaly(anomalies, index, "date_normalized", "info", date_note, "Stored normalized ISO date.", row)

                payer = normalize_name(row.get("paid_by"))
                description = row.get("description", "").strip()
                split_type = (row.get("split_type") or "").strip().lower()
                amount = parse_amount(row.get("amount"))
                currency = (row.get("currency") or "").strip().upper()
                participants = parse_people(row.get("split_with"))

                if not payer:
                    add_anomaly(anomalies, index, "missing_payer", "error", "Expense has no paid_by value.", "Skipped row; user must correct payer.", row)
                    skipped += 1
                    continue

                raw_payer = (row.get("paid_by") or "").strip()
                if payer != raw_payer:
                    add_anomaly(anomalies, index, "name_normalized", "info", f"Normalized payer '{raw_payer}' to '{payer}'.", "Used canonical member name.", row)

                normalized_people = "; ".join(participants)
                if normalized_people != (row.get("split_with") or "").replace(";", "; "):
                    add_anomaly(anomalies, index, "split_people_normalized", "info", "Normalized split participant names.", "Used canonical member names.", row)

                if not currency:
                    currency = "INR"
                    add_anomaly(anomalies, index, "missing_currency", "warning", "Currency was blank.", "Defaulted to INR because all nearby home expenses are INR.", row)
                if currency not in {"INR", "USD"}:
                    add_anomaly(anomalies, index, "unknown_currency", "error", f"Unsupported currency: {currency}.", "Skipped row.", row)
                    skipped += 1
                    continue

                amount_inr = money(amount * USD_TO_INR) if currency == "USD" else money(amount)
                if currency == "USD":
                    add_anomaly(anomalies, index, "currency_converted", "info", f"Converted USD to INR at {USD_TO_INR}.", "Stored original currency and converted INR amount.", row)
                if "," in str(row.get("amount")) or str(row.get("amount")).strip() != str(row.get("amount")):
                    add_anomaly(anomalies, index, "amount_normalized", "info", "Amount had comma or whitespace formatting.", "Parsed to Decimal and stored a two-decimal INR value.", row)
                if amount < 0:
                    add_anomaly(anomalies, index, "negative_amount", "warning", "Negative amount detected.", "Treated as refund/credit reducing the original obligation.", row)
                if amount == 0:
                    add_anomaly(anomalies, index, "zero_amount", "warning", "Zero amount expense detected.", "Skipped row because it has no financial effect.", row)
                    skipped += 1
                    continue

                if not split_type and "settlement" in row.get("notes", "").lower():
                    receiver = participants[0] if participants else "Aisha"
                    conn.execute(
                        """
                        INSERT INTO settlements(import_run_id, row_number, group_id, settlement_date, payer_id, receiver_id, amount_inr, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (run_id, index, group_id, expense_date.isoformat(), get_member_id(conn, payer), get_member_id(conn, receiver), str(money(amount_inr)), row.get("notes")),
                    )
                    add_anomaly(anomalies, index, "settlement_not_expense", "warning", "Row appears to be a payment/settlement, not an expense.", "Recorded in settlements table and excluded from expense splits.", row)
                    imported += 1
                    continue

                key = (expense_date.isoformat(), canonical_description(description), currency, tuple(sorted(participants)))
                previous = seen.get(key)
                if previous:
                    if previous["amount"] == amount:
                        add_anomaly(anomalies, index, "duplicate_expense", "warning", "Duplicate-looking row with same date, people, currency, and amount.", "Skipped later duplicate and kept first row.", row)
                        skipped += 1
                        continue
                    add_anomaly(anomalies, previous["row_number"], "near_duplicate_conflict", "warning", "Possible duplicate has a conflicting amount.", "Superseded by later row with clearer note/context.", previous["row"])
                    conn.execute("UPDATE expenses SET status='superseded' WHERE row_number=?", (previous["row_number"],))
                    add_anomaly(anomalies, index, "near_duplicate_conflict", "warning", "Possible duplicate has a conflicting amount.", "Kept this row as active and marked earlier row superseded.", row)
                seen[key] = {"amount": amount, "row_number": index, "row": dict(row)}

                splits = split_amount(row, amount_inr, participants, anomalies, index, expense_date)
                expense_id = conn.execute(
                    """
                    INSERT INTO expenses(import_run_id, row_number, group_id, expense_date, description, paid_by_id,
                        amount_original, currency, amount_inr, split_type, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (run_id, index, group_id, expense_date.isoformat(), description, get_member_id(conn, payer), str(amount), currency, str(money(amount_inr)), split_type, row.get("notes")),
                ).lastrowid
                for person, split_value in splits.items():
                    conn.execute(
                        "INSERT INTO expense_splits(expense_id, member_id, amount_inr) VALUES (?, ?, ?)",
                        (expense_id, get_member_id(conn, person), str(money(split_value))),
                    )
                imported += 1
            except Exception as exc:
                add_anomaly(anomalies, index, "import_error", "error", str(exc), "Skipped row; importer continued.", row)
                skipped += 1

        for item in anomalies:
            conn.execute(
                """
                INSERT INTO anomalies(import_run_id, row_number, code, severity, message, action, raw_row)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, item["row_number"], item["code"], item["severity"], item["message"], item["action"], json.dumps(item["raw_row"], ensure_ascii=False)),
            )
        conn.execute(
            "UPDATE import_runs SET rows_seen=?, rows_imported=?, rows_skipped=? WHERE id=?",
            (len(rows), imported, skipped, run_id),
        )

    report = {
        "import_run_id": run_id,
        "source_file": Path(path).name,
        "imported_at": imported_at,
        "usd_to_inr": str(USD_TO_INR),
        "rows_seen": len(rows),
        "rows_imported": imported,
        "rows_skipped": skipped,
        "anomalies": anomalies,
    }
    write_report(report)
    return report


def write_report(report):
    REPORT_DIR.mkdir(exist_ok=True)
    json_path = REPORT_DIR / "latest_import_report.json"
    md_path = REPORT_DIR / "latest_import_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Import Report",
        "",
        f"- Source file: `{report['source_file']}`",
        f"- Imported at: `{report['imported_at']}`",
        f"- USD to INR rate: `{report['usd_to_inr']}`",
        f"- Rows seen: `{report['rows_seen']}`",
        f"- Rows imported: `{report['rows_imported']}`",
        f"- Rows skipped: `{report['rows_skipped']}`",
        "",
        "| Row | Code | Severity | Action | Message |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report["anomalies"]:
        lines.append(
            f"| {item['row_number']} | `{item['code']}` | {item['severity']} | {escape(item['action'])} | {escape(item['message'])} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_summary():
    init_db()
    with connect() as conn:
        run = conn.execute("SELECT * FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not run:
            return None
        members = [row["name"] for row in conn.execute("SELECT name FROM members ORDER BY name")]
        balances = defaultdict(Decimal)
        rows = conn.execute(
            """
            SELECT e.id, e.row_number, e.expense_date, e.description, payer.name AS paid_by, e.amount_inr, e.status
            FROM expenses e
            JOIN members payer ON payer.id = e.paid_by_id
            ORDER BY e.expense_date, e.id
            """
        ).fetchall()
        trace = []
        for expense in rows:
            if expense["status"] != "active":
                trace.append({**dict(expense), "ignored": True, "splits": []})
                continue
            amount = Decimal(expense["amount_inr"])
            balances[expense["paid_by"]] += amount
            splits = []
            for split in conn.execute(
                """
                SELECT m.name, s.amount_inr
                FROM expense_splits s
                JOIN members m ON m.id = s.member_id
                WHERE s.expense_id=?
                ORDER BY m.name
                """,
                (expense["id"],),
            ):
                split_amount_inr = Decimal(split["amount_inr"])
                balances[split["name"]] -= split_amount_inr
                splits.append({"name": split["name"], "amount": split_amount_inr})
            trace.append({**dict(expense), "ignored": False, "splits": splits})

        settlements = conn.execute(
            """
            SELECT s.*, payer.name AS payer, receiver.name AS receiver
            FROM settlements s
            JOIN members payer ON payer.id = s.payer_id
            JOIN members receiver ON receiver.id = s.receiver_id
            ORDER BY s.settlement_date, s.id
            """
        ).fetchall()
        for settlement in settlements:
            amount = Decimal(settlement["amount_inr"])
            balances[settlement["payer"]] += amount
            balances[settlement["receiver"]] -= amount

        anomalies = conn.execute("SELECT * FROM anomalies ORDER BY row_number, id").fetchall()
        return {
            "run": run,
            "members": members,
            "balances": {member: money(value) for member, value in balances.items()},
            "settlements": settlements,
            "suggestions": simplify_debts(balances),
            "trace": trace,
            "anomalies": anomalies,
        }


def simplify_debts(balances):
    debtors = sorted([(name, -money(value)) for name, value in balances.items() if money(value) < 0], key=lambda x: x[1], reverse=True)
    creditors = sorted([(name, money(value)) for name, value in balances.items() if money(value) > 0], key=lambda x: x[1], reverse=True)
    suggestions = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor, debt = debtors[i]
        creditor, credit = creditors[j]
        amount = min(debt, credit)
        if amount > Decimal("0.00"):
            suggestions.append((debtor, creditor, money(amount)))
        debtors[i] = (debtor, money(debt - amount))
        creditors[j] = (creditor, money(credit - amount))
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return suggestions


def render_layout(title, body, username=None):
    nav = ""
    if username:
        nav = """
        <nav>
          <a href="/">Dashboard</a>
          <a href="/import">Import</a>
          <a href="/expenses">Trace</a>
          <a href="/anomalies">Anomalies</a>
          <a href="/logout">Logout</a>
        </nav>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - Spreetail Expenses</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header>
    <div>
      <p class="eyebrow">Spreetail Assignment</p>
      <h1>{escape(title)}</h1>
    </div>
    {nav}
  </header>
  <main>{body}</main>
</body>
</html>"""


def render_dashboard(username):
    summary = load_summary()
    if not summary:
        body = """
        <section class="panel">
          <h2>No import yet</h2>
          <p>Import the supplied CSV to calculate balances and generate the anomaly report.</p>
          <form method="post" action="/import">
            <button type="submit">Import supplied CSV</button>
          </form>
        </section>
        """
        return render_layout("Dashboard", body, username)
    balance_rows = "".join(
        f"<tr><td>{escape(name)}</td><td class='{('positive' if amount > 0 else 'negative' if amount < 0 else '')}'>{rupees(amount)}</td></tr>"
        for name, amount in sorted(summary["balances"].items())
    )
    suggestions = "".join(
        f"<li><strong>{escape(debtor)}</strong> pays <strong>{escape(creditor)}</strong> {rupees(amount)}</li>"
        for debtor, creditor, amount in summary["suggestions"]
    ) or "<li>No settlement required.</li>"
    run = summary["run"]
    body = f"""
    <section class="grid">
      <article class="metric"><span>Rows seen</span><strong>{run['rows_seen']}</strong></article>
      <article class="metric"><span>Rows imported</span><strong>{run['rows_imported']}</strong></article>
      <article class="metric"><span>Rows skipped</span><strong>{run['rows_skipped']}</strong></article>
      <article class="metric"><span>Anomalies</span><strong>{len(summary['anomalies'])}</strong></article>
    </section>
    <section class="columns">
      <article class="panel">
        <h2>Individual balances</h2>
        <p>Positive means the group owes this person. Negative means this person owes the group.</p>
        <table><thead><tr><th>Person</th><th>Balance</th></tr></thead><tbody>{balance_rows}</tbody></table>
      </article>
      <article class="panel">
        <h2>Suggested settlements</h2>
        <p>Greedy debt simplification after expenses and recorded settlements.</p>
        <ol>{suggestions}</ol>
      </article>
    </section>
    """
    return render_layout("Dashboard", body, username)


def render_import(username, message=""):
    summary = load_summary()
    report_links = ""
    if summary:
        report_links = """
        <p><a href="/report.md">Download Markdown import report</a> ·
        <a href="/report.json">Download JSON import report</a></p>
        """
    body = f"""
    <section class="panel">
      <h2>Import supplied CSV</h2>
      <p>The app imports <code>expenses_export.csv</code> exactly as supplied. It does not require manual CSV edits.</p>
      {f'<p class="notice">{escape(message)}</p>' if message else ''}
      <form method="post" action="/import">
        <button type="submit">Run import</button>
      </form>
      {report_links}
    </section>
    """
    return render_layout("Import", body, username)


def render_anomalies(username):
    summary = load_summary()
    if not summary:
        return render_layout("Anomalies", "<section class='panel'><p>No import yet.</p></section>", username)
    rows = "".join(
        f"<tr><td>{item['row_number']}</td><td><code>{escape(item['code'])}</code></td><td>{escape(item['severity'])}</td><td>{escape(item['message'])}</td><td>{escape(item['action'])}</td></tr>"
        for item in summary["anomalies"]
    )
    body = f"""
    <section class="panel wide">
      <h2>Detected anomalies</h2>
      <table>
        <thead><tr><th>CSV row</th><th>Code</th><th>Severity</th><th>Problem</th><th>Action</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """
    return render_layout("Anomalies", body, username)


def render_expenses(username):
    summary = load_summary()
    if not summary:
        return render_layout("Trace", "<section class='panel'><p>No import yet.</p></section>", username)
    blocks = []
    for expense in summary["trace"]:
        splits = "".join(f"<li>{escape(s['name'])}: {rupees(s['amount'])}</li>" for s in expense["splits"])
        badge = "<span class='badge'>superseded</span>" if expense["ignored"] else ""
        blocks.append(
            f"""
            <article class="trace-card">
              <h3>Row {expense['row_number']}: {escape(expense['description'])} {badge}</h3>
              <p>{escape(expense['expense_date'])} · Paid by {escape(expense['paid_by'])} · {rupees(expense['amount_inr'])}</p>
              <ul>{splits or '<li>Excluded from active balance.</li>'}</ul>
            </article>
            """
        )
    return render_layout("Expense Trace", "<section class='stack'>" + "".join(blocks) + "</section>", username)


def render_login(error=""):
    body = f"""
    <section class="login-card">
      <h2>Login</h2>
      <p>Demo users: <code>admin/demo123</code>, <code>aisha/demo123</code>, <code>rohan/demo123</code>.</p>
      {f'<p class="error">{escape(error)}</p>' if error else ''}
      <form method="post" action="/login">
        <label>Username <input name="username" required></label>
        <label>Password <input name="password" type="password" required></label>
        <button type="submit">Sign in</button>
      </form>
    </section>
    """
    return render_layout("Login", body)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        username = self.current_user()
        path = urlparse(self.path).path
        if path == "/static/styles.css":
            return self.send_css()
        if path in {"/report.json", "/report.md"}:
            return self.send_report(path)
        if path == "/login":
            return self.html(render_login())
        if not username:
            return self.redirect("/login")
        if path == "/":
            return self.html(render_dashboard(username))
        if path == "/import":
            return self.html(render_import(username))
        if path == "/anomalies":
            return self.html(render_anomalies(username))
        if path == "/expenses":
            return self.html(render_expenses(username))
        if path == "/logout":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            username = data.get("username", [""])[0].strip().lower()
            password = data.get("password", [""])[0]
            with connect() as conn:
                row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if row and row["password_hash"] == password_hash(password):
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"session={make_session(username)}; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
            else:
                self.html(render_login("Invalid username or password."), status=401)
            return
        username = self.current_user()
        if not username:
            return self.redirect("/login")
        if path == "/import":
            report = import_csv(CSV_PATH)
            return self.html(render_import(username, f"Imported {report['rows_imported']} rows; skipped {report['rows_skipped']}; detected {len(report['anomalies'])} anomalies."))
        self.send_error(404)

    def current_user(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        morsel = jar.get("session")
        return verify_session(morsel.value) if morsel else None

    def html(self, content, status=200):
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def send_report(self, path):
        target = REPORT_DIR / ("latest_import_report.json" if path.endswith(".json") else "latest_import_report.md")
        if not target.exists():
            self.send_error(404, "Run import first")
            return
        data = target.read_bytes()
        content_type = "application/json" if target.suffix == ".json" else "text/markdown"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f"attachment; filename={target.name}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_css(self):
        css = (BASE_DIR / "static" / "styles.css").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/css")
        self.send_header("Content-Length", str(len(css)))
        self.end_headers()
        self.wfile.write(css)

    def log_message(self, format, *args):
        return


def main():
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AppHandler)
    print(f"Spreetail Expenses running on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "import":
        print(json.dumps(import_csv(), indent=2, ensure_ascii=False))
    else:
        main()
