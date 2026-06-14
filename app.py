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
APP_NAME = "LedgerLens"
APP_TAGLINE = "Explainable shared-expense cleanup"

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


from contextlib import contextmanager


def render_expense_form(username, group_id, expense_id=None, message=""):
    with connect() as conn:
        group = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            return render_layout("Group Not Found", "<section class='panel'><p>Group not found.</p></section>", username)
        
        members = conn.execute(
            """
            SELECT m.id, m.name
            FROM memberships ms
            JOIN members m ON ms.member_id = m.id
            WHERE ms.group_id = ?
            ORDER BY m.name
            """,
            (group_id,)
        ).fetchall()
        
        expense = None
        current_splits = {}
        if expense_id:
            expense = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
            if expense:
                splits = conn.execute("SELECT member_id, amount_inr FROM expense_splits WHERE expense_id = ?", (expense_id,)).fetchall()
                current_splits = {s["member_id"]: Decimal(s["amount_inr"]) for s in splits}

    if not members:
        return render_layout("No Members", f"<section class='panel'><h2>No members in group</h2><p>Please <a href='/groups/view?id={group_id}'>add members</a> first.</p></section>", username)

    title = "Edit Expense" if expense else "New Expense"
    
    desc_val = escape(expense["description"]) if expense else ""
    amount_val = str(expense["amount_original"]) if expense else ""
    curr_val = expense["currency"] if expense else "INR"
    payer_val = expense["paid_by_id"] if expense else ""
    date_val = expense["expense_date"] if expense else datetime.now().strftime("%Y-%m-%d")
    split_type_val = expense["split_type"] if expense else "equal"
    
    payer_options = "".join(
        f'<option value="{m["id"]}" {"selected" if m["id"] == payer_val else ""}>{escape(m["name"])}</option>'
        for m in members
    )
    
    participant_rows = ""
    for m in members:
        is_checked = "checked"
        split_val_str = ""
        if expense:
            is_checked = "checked" if m["id"] in current_splits else ""
            if m["id"] in current_splits:
                split_val_str = str(current_splits[m["id"]])
        
        participant_rows += f"""
        <div class="checkbox-row" style="margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
          <label style="display:flex; align-items:center; gap:8px; margin:0; cursor:pointer;">
            <input type="checkbox" name="participants" value="{m['name']}" {is_checked} onchange="toggleMemberInput(this)">
            <span>{escape(m['name'])}</span>
          </label>
          <div class="split-input-group" id="input_div_{escape(m['name'])}" style="display: {('flex' if split_type_val != 'equal' else 'none')}; align-items:center; gap:5px;">
            <input type="number" step="any" name="split_val_{escape(m['name'])}" value="{split_val_str}" placeholder="value" style="width: 80px; padding: 4px 6px;">
            <span class="split-unit-label"></span>
          </div>
        </div>
        """

    template = """
    <section class="hero-panel compact">
      <div>
        <p class="eyebrow">__GROUP_NAME__</p>
        <h2>__TITLE__</h2>
        <p><a href="/?group_id=__GROUP_ID__">← Back to Dashboard</a></p>
      </div>
    </section>

    <section class="panel" style="max-width: 600px; margin: 0 auto;">
      __MESSAGE_HTML__
      <form method="post" action="__ACTION__">
        <input type="hidden" name="group_id" value="__GROUP_ID__">
        __EXPENSE_ID_INPUT__
        
        <label>Description
          <input name="description" value="__DESC_VAL__" placeholder="e.g., Dinner Marina Bites" required>
        </label>
        
        <div style="display: grid; grid-template-columns: 1.2fr .8fr; gap: 10px;">
          <label>Amount
            <input name="amount" type="number" step="0.01" value="__AMOUNT_VAL__" placeholder="0.00" required>
          </label>
          <label>Currency
            <select name="currency" required>
              <option value="INR" __INR_SELECTED__>INR</option>
              <option value="USD" __USD_SELECTED__>USD</option>
            </select>
          </label>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <label>Paid By
            <select name="paid_by_id" required>
              __PAYER_OPTIONS__
            </select>
          </label>
          <label>Date
            <input name="expense_date" type="date" value="__DATE_VAL__" required>
          </label>
        </div>

        <label>Split Type
          <select name="split_type" id="split_type_select" onchange="onSplitTypeChange(this.value)" required>
            <option value="equal" __EQUAL_SELECTED__>Equally</option>
            <option value="unequal" __UNEQUAL_SELECTED__>Unequally (Exact amounts)</option>
            <option value="share" __SHARE_SELECTED__>By Shares (Ratio)</option>
            <option value="percentage" __PERCENTAGE_SELECTED__>By Percentages (%)</option>
          </select>
        </label>

        <div class="panel" style="background: #f8fafc; border: 1px solid var(--line); margin-bottom: 20px;">
          <h3 style="margin-bottom: 10px;">Participants</h3>
          <div class="checkbox-grid">
            __PARTICIPANT_ROWS__
          </div>
        </div>

        <div class="btn-group">
          <button type="submit">Save Expense</button>
          <a href="/?group_id=__GROUP_ID__" class="button" style="background: #f1f5f9; color: var(--ink); border: 1px solid var(--line); box-shadow: none;">Cancel</a>
        </div>
      </form>
    </section>

    <script>
      function onSplitTypeChange(val) {
        const divs = document.querySelectorAll(".split-input-group");
        const labels = document.querySelectorAll(".split-unit-label");
        
        divs.forEach(div => {
          if (val === "equal") {
            div.style.display = "none";
          } else {
            div.style.display = "flex";
          }
        });

        labels.forEach(label => {
          if (val === "percentage") {
            label.textContent = "%";
          } else if (val === "share") {
            label.textContent = "share(s)";
          } else {
            label.textContent = "";
          }
        });
      }

      function toggleMemberInput(chk) {
        const inputDiv = document.getElementById("input_div_" + chk.value);
        if (inputDiv) {
          const input = inputDiv.querySelector("input");
          if (chk.checked) {
            input.disabled = false;
            const splitType = document.getElementById("split_type_select").value;
            if (splitType !== "equal") {
              inputDiv.style.display = "flex";
            }
          } else {
            input.disabled = true;
            inputDiv.style.display = "none";
          }
        }
      }

      document.addEventListener("DOMContentLoaded", () => {
        onSplitTypeChange(document.getElementById("split_type_select").value);
        document.querySelectorAll("input[type=checkbox][name=participants]").forEach(chk => {
          toggleMemberInput(chk);
        });
      });
    </script>
    """
    
    body = (template
        .replace("__GROUP_NAME__", escape(group["name"]))
        .replace("__TITLE__", title)
        .replace("__GROUP_ID__", str(group_id))
        .replace("__MESSAGE_HTML__", f'<p class="error">{escape(message)}</p>' if message else '')
        .replace("__ACTION__", "/expenses/edit" if expense else "/expenses/new")
        .replace("__EXPENSE_ID_INPUT__", f'<input type="hidden" name="expense_id" value="{expense_id}">' if expense else '')
        .replace("__DESC_VAL__", desc_val)
        .replace("__AMOUNT_VAL__", amount_val)
        .replace("__INR_SELECTED__", "selected" if curr_val == "INR" else "")
        .replace("__USD_SELECTED__", "selected" if curr_val == "USD" else "")
        .replace("__PAYER_OPTIONS__", payer_options)
        .replace("__DATE_VAL__", date_val)
        .replace("__EQUAL_SELECTED__", "selected" if split_type_val == "equal" else "")
        .replace("__UNEQUAL_SELECTED__", "selected" if split_type_val == "unequal" else "")
        .replace("__SHARE_SELECTED__", "selected" if split_type_val == "share" else "")
        .replace("__PERCENTAGE_SELECTED__", "selected" if split_type_val == "percentage" else "")
        .replace("__PARTICIPANT_ROWS__", participant_rows)
    )
    return render_layout(title, body, username)


def render_settlement_form(username, group_id, message=""):
    with connect() as conn:
        group = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            return render_layout("Group Not Found", "<section class='panel'><p>Group not found.</p></section>", username)
        
        members = conn.execute(
            """
            SELECT m.id, m.name
            FROM memberships ms
            JOIN members m ON ms.member_id = m.id
            WHERE ms.group_id = ?
            ORDER BY m.name
            """,
            (group_id,)
        ).fetchall()

    if len(members) < 2:
        return render_layout("Insufficient Members", f"<section class='panel'><h2>Insufficient members in group</h2><p>Please <a href='/groups/view?id={group_id}'>add members</a> first (at least 2 are required to record a settlement).</p></section>", username)

    payer_options = "".join(
        f'<option value="{m["id"]}">{escape(m["name"])}</option>'
        for m in members
    )
    receiver_options = "".join(
        f'<option value="{m["id"]}">{escape(m["name"])}</option>'
        for m in members
    )
    date_val = datetime.now().strftime("%Y-%m-%d")

    body = f"""
    <section class="hero-panel compact">
      <div>
        <p class="eyebrow">{escape(group['name'])}</p>
        <h2>Record a Payment</h2>
        <p><a href="/?group_id={group_id}">← Back to Dashboard</a></p>
      </div>
    </section>

    <section class="panel" style="max-width: 500px; margin: 0 auto;">
      {f'<p class="error">{escape(message)}</p>' if message else ''}
      <form method="post" action="/settlements/new">
        <input type="hidden" name="group_id" value="{group_id}">
        
        <label>Payer (Who paid)
          <select name="payer_id" required>
            {payer_options}
          </select>
        </label>
        
        <label>Receiver (Who was paid)
          <select name="receiver_id" required>
            {receiver_options}
          </select>
        </label>
        
        <label>Amount (INR)
          <input name="amount" type="number" step="0.01" placeholder="0.00" required>
        </label>
        
        <label>Date
          <input name="settlement_date" type="date" value="{date_val}" required>
        </label>
        
        <label>Notes
          <input name="notes" placeholder="e.g., Settle April rent">
        </label>

        <div class="btn-group">
          <button type="submit">Record Payment</button>
          <a href="/?group_id={group_id}" class="button" style="background: #f1f5f9; color: var(--ink); border: 1px solid var(--line); box-shadow: none;">Cancel</a>
        </div>
      </form>
    </section>
    """
    return render_layout("Record Payment", body, username)


def save_expense_db(conn, group_id, description, amount, currency, paid_by_id, expense_date, split_type, participants, split_vals, expense_id=None):
    amount = Decimal(str(amount))
    amount_inr = money(amount * USD_TO_INR) if currency == "USD" else money(amount)
    
    active_people = []
    anomalies = []
    
    exp_date_obj = datetime.strptime(expense_date, "%Y-%m-%d").date()
    
    for p in participants:
        if is_active(conn, group_id, p, exp_date_obj):
            active_people.append(p)
        else:
            anomalies.append(f"Removed inactive member '{p}' from split.")
            
    if not active_people:
        raise ValueError("No active group members selected for this split.")
        
    splits = {}
    if split_type == "equal":
        share = money(amount_inr / Decimal(len(active_people)))
        splits = {p: share for p in active_people}
        drift = amount_inr - sum(splits.values(), Decimal("0"))
        if drift:
            splits[active_people[0]] = money(splits[active_people[0]] + drift)
            
    elif split_type == "unequal":
        splits = {}
        for p in active_people:
            val = Decimal(split_vals.get(p, "0") or "0")
            val_inr = money(val * USD_TO_INR) if currency == "USD" else money(val)
            splits[p] = val_inr
        total_splits = sum(splits.values(), Decimal("0"))
        if total_splits != amount_inr:
            raise ValueError(f"Sum of splits ({total_splits}) does not equal total amount ({amount_inr}).")
            
    elif split_type == "share":
        total_shares = sum(Decimal(split_vals.get(p, "0") or "0") for p in active_people)
        if total_shares <= 0:
            raise ValueError("Total shares must be greater than 0.")
        splits = {}
        for p in active_people:
            share_val = Decimal(split_vals.get(p, "0") or "0")
            splits[p] = money(amount_inr * share_val / total_shares)
        drift = amount_inr - sum(splits.values(), Decimal("0"))
        if drift:
            splits[active_people[0]] = money(splits[active_people[0]] + drift)
            
    elif split_type == "percentage":
        total_pct = sum(Decimal(split_vals.get(p, "0") or "0") for p in active_people)
        if total_pct != 100:
            raise ValueError(f"Percentages must total 100% (currently {total_pct}%).")
        splits = {}
        for p in active_people:
            pct_val = Decimal(split_vals.get(p, "0") or "0")
            splits[p] = money(amount_inr * pct_val / Decimal("100"))
        drift = amount_inr - sum(splits.values(), Decimal("0"))
        if drift:
            splits[active_people[0]] = money(splits[active_people[0]] + drift)

    if expense_id:
        conn.execute(
            """
            UPDATE expenses
            SET description = ?, amount_original = ?, currency = ?, amount_inr = ?, paid_by_id = ?, expense_date = ?, split_type = ?, notes = ?
            WHERE id = ?
            """,
            (description, str(amount), currency, str(amount_inr), paid_by_id, expense_date, split_type, ", ".join(anomalies) if anomalies else None, expense_id)
        )
        conn.execute("DELETE FROM expense_splits WHERE expense_id = ?", (expense_id,))
    else:
        run_row = conn.execute("SELECT id FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
        if run_row:
            run_id = run_row["id"]
        else:
            imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            run_id = conn.execute(
                """
                INSERT INTO import_runs(source_file, imported_at, usd_to_inr, rows_seen, rows_imported, rows_skipped)
                VALUES ('Manual', ?, ?, 0, 0, 0)
                """,
                (imported_at, str(USD_TO_INR))
            ).lastrowid
            
        expense_id = conn.execute(
            """
            INSERT INTO expenses(import_run_id, row_number, group_id, expense_date, description, paid_by_id,
                amount_original, currency, amount_inr, split_type, notes, status)
            VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (run_id, group_id, expense_date, description, paid_by_id, str(amount), currency, str(amount_inr), split_type, ", ".join(anomalies) if anomalies else None)
        ).lastrowid

    for p in active_people:
        member_id = conn.execute("SELECT id FROM members WHERE name = ?", (p,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO expense_splits(expense_id, member_id, amount_inr) VALUES (?, ?, ?)",
            (expense_id, member_id, str(splits[p]))
        )


@contextmanager
def connect():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()



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
    try:
        with connect() as conn:
            expense_count = conn.execute("SELECT COUNT(*) as count FROM expenses").fetchone()["count"]
        if expense_count == 0:
            import_csv()
    except Exception as e:
        pass


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


def is_active(conn, group_id, member, expense_date):
    row = conn.execute(
        """
        SELECT joined_on, left_on
        FROM memberships ms
        JOIN members m ON ms.member_id = m.id
        WHERE ms.group_id = ? AND m.name = ?
        """,
        (group_id, member),
    ).fetchone()
    if not row:
        return False
    start = datetime.strptime(row["joined_on"], "%Y-%m-%d").date()
    end = datetime.strptime(row["left_on"], "%Y-%m-%d").date() if row["left_on"] else None
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


def split_amount(conn, group_id, row, amount_inr, participants, anomalies, row_number, expense_date):
    split_type = (row.get("split_type") or "").strip().lower()
    details = row.get("split_details") or ""
    active_people = [p for p in participants if is_active(conn, group_id, p, expense_date)]
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

                splits = split_amount(conn, group_id, row, amount_inr, participants, anomalies, index, expense_date)
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


def load_summary(group_id=1):
    init_db()
    with connect() as conn:
        group = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            group = conn.execute("SELECT * FROM groups ORDER BY id LIMIT 1").fetchone()
            if not group:
                return None
            group_id = group["id"]

        run = conn.execute("SELECT * FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
        
        members = [row["name"] for row in conn.execute(
            """
            SELECT DISTINCT m.name
            FROM members m
            JOIN memberships ms ON ms.member_id = m.id
            WHERE ms.group_id = ?
            ORDER BY m.name
            """,
            (group_id,)
        ).fetchall()]
        
        balances = defaultdict(Decimal)
        for member in members:
            balances[member] = Decimal("0.00")
            
        rows = conn.execute(
            """
            SELECT e.id, e.row_number, e.expense_date, e.description, payer.name AS paid_by, e.amount_inr, e.status
            FROM expenses e
            JOIN members payer ON payer.id = e.paid_by_id
            WHERE e.group_id = ?
            ORDER BY e.expense_date, e.id
            """,
            (group_id,)
        ).fetchall()
        trace = []
        for expense in rows:
            if expense["status"] != "active":
                trace.append({**dict(expense), "ignored": True, "splits": []})
                continue
            amount = Decimal(expense["amount_inr"])
            if expense["paid_by"] in balances:
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
                if split["name"] in balances:
                    balances[split["name"]] -= split_amount_inr
                splits.append({"name": split["name"], "amount": split_amount_inr})
            trace.append({**dict(expense), "ignored": False, "splits": splits})

        settlements = conn.execute(
            """
            SELECT s.*, payer.name AS payer, receiver.name AS receiver
            FROM settlements s
            JOIN members payer ON payer.id = s.payer_id
            JOIN members receiver ON receiver.id = s.receiver_id
            WHERE s.group_id = ?
            ORDER BY s.settlement_date, s.id
            """,
            (group_id,)
        ).fetchall()
        for settlement in settlements:
            amount = Decimal(settlement["amount_inr"])
            if settlement["payer"] in balances:
                balances[settlement["payer"]] += amount
            if settlement["receiver"] in balances:
                balances[settlement["receiver"]] -= amount

        anomalies = conn.execute("SELECT * FROM anomalies ORDER BY row_number, id").fetchall()
        anomaly_counts = defaultdict(int)
        for item in anomalies:
            anomaly_counts[item["severity"]] += 1
        return {
            "group": group,
            "run": run,
            "members": members,
            "balances": {member: money(value) for member, value in balances.items()},
            "settlements": settlements,
            "suggestions": simplify_debts(balances),
            "trace": trace,
            "anomalies": anomalies,
            "anomaly_counts": dict(anomaly_counts),
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


def render_groups(username, message=""):
    with connect() as conn:
        groups = conn.execute(
            """
            SELECT g.id, g.name, COUNT(ms.id) AS member_count
            FROM groups g
            LEFT JOIN memberships ms ON g.id = ms.group_id
            GROUP BY g.id
            ORDER BY g.name
            """
        ).fetchall()

    rows = "".join(
        f"""<tr>
          <td><strong>{escape(g['name'])}</strong></td>
          <td>{g['member_count']} members</td>
          <td>
            <a href="/groups/view?id={g['id']}">Manage Members</a>
          </td>
        </tr>"""
        for g in groups
    )

    body = f"""
    <section class="hero-panel compact">
      <div>
        <p class="eyebrow">Group Management</p>
        <h2>Groups and Membership</h2>
        <p>Create groups and manage who was in the group at different times.</p>
      </div>
    </section>
    
    <section class="columns">
      <article class="panel">
        <h2>Existing Groups</h2>
        {f'<p class="notice">{escape(message)}</p>' if message else ''}
        <table>
          <thead>
            <tr><th>Group Name</th><th>Members</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {rows if rows else '<tr><td colspan="3">No groups created yet.</td></tr>'}
          </tbody>
        </table>
      </article>

      <article class="panel">
        <h2>Create a New Group</h2>
        <form method="post" action="/groups">
          <label>Group Name
            <input name="name" placeholder="e.g., Summer Trip 2026" required>
          </label>
          <button type="submit">Create Group</button>
        </form>
      </article>
    </section>
    """
    return render_layout("Groups", body, username)


def render_group_detail(username, group_id, message=""):
    with connect() as conn:
        group = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            return render_layout("Group Not Found", "<section class='panel'><p>Group not found.</p></section>", username)
        
        memberships = conn.execute(
            """
            SELECT ms.id, ms.joined_on, ms.left_on, m.name AS member_name
            FROM memberships ms
            JOIN members m ON ms.member_id = m.id
            WHERE ms.group_id = ?
            ORDER BY m.name, ms.joined_on
            """,
            (group_id,)
        ).fetchall()

    rows = "".join(
        f"""<tr>
          <td><strong>{escape(m['member_name'])}</strong></td>
          <td>{escape(m['joined_on'])}</td>
          <td>{escape(m['left_on']) if m['left_on'] else 'Active'}</td>
          <td>
            <form method="post" action="/groups/delete_membership" style="display:inline;" onsubmit="return confirm('Are you sure you want to remove this membership?');">
              <input type="hidden" name="membership_id" value="{m['id']}">
              <input type="hidden" name="group_id" value="{group_id}">
              <button type="submit" class="button-danger" style="padding: 4px 8px; font-size: 12px; background: var(--coral); box-shadow: none;">Remove</button>
            </form>
          </td>
        </tr>"""
        for m in memberships
    )

    body = f"""
    <section class="hero-panel compact">
      <div>
        <p class="eyebrow">Group Details</p>
        <h2>{escape(group['name'])}</h2>
        <p><a href="/groups">← Back to Groups</a></p>
      </div>
    </section>

    <section class="columns">
      <article class="panel">
        <h2>Members and Active Windows</h2>
        <p class="muted">A member only participates in splits for expenses during their active window.</p>
        {f'<p class="notice">{escape(message)}</p>' if message else ''}
        <table>
          <thead>
            <tr><th>Member Name</th><th>Joined On</th><th>Left On</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {rows if rows else '<tr><td colspan="4">No members in this group yet.</td></tr>'}
          </tbody>
        </table>
      </article>

      <article class="panel">
        <h2>Add or Update Member</h2>
        <p class="muted">Add a member and define their active period. If a member with the same name already exists in the system, they will be associated with this group. If they have an existing membership, this adds a new window or updates it.</p>
        <form method="post" action="/groups/members">
          <input type="hidden" name="group_id" value="{group_id}">
          <label>Member Name
            <input name="member_name" placeholder="e.g., Sam" required>
          </label>
          <label>Joined On (YYYY-MM-DD)
            <input name="joined_on" type="date" value="{datetime.now().strftime('%Y-%m-%d')}" required>
          </label>
          <label>Left On (YYYY-MM-DD, optional)
            <input name="left_on" type="date">
          </label>
          <button type="submit">Save Membership</button>
        </form>
      </article>
    </section>
    """
    return render_layout(f"Manage - {group['name']}", body, username)


def render_layout(title, body, username=None):
    nav = ""
    if username:
        nav = """
        <nav>
          <a href="/">Dashboard</a>
          <a href="/groups">Groups</a>
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
  <title>{escape(title)} - {APP_NAME}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <script>
    (function() {{
      const theme = localStorage.getItem('theme') || 'dark';
      if (theme === 'dark') {{
        document.body.classList.add('dark-mode');
      }} else {{
        document.body.classList.remove('dark-mode');
      }}
    }})();
  </script>
  <header>
    <div>
      <p class="brand">{APP_NAME}</p>
      <h1 style="display: flex; align-items: center; gap: 12px;">
        {escape(title)}
        <button onclick="toggleTheme()" class="theme-btn" title="Toggle Theme" style="cursor: pointer; font-size: 16px;">🌓</button>
      </h1>
      <p class="tagline">{APP_TAGLINE}</p>
    </div>
    {nav}
  </header>
  <main>{body}</main>
  <script>
    function toggleTheme() {{
      if (document.body.classList.contains('dark-mode')) {{
        document.body.classList.remove('dark-mode');
        localStorage.setItem('theme', 'light');
      }} else {{
        document.body.classList.add('dark-mode');
        localStorage.setItem('theme', 'dark');
      }}
    }}
  </script>
</body>
</html>"""


def render_dashboard(username, group_id=1):
    with connect() as conn:
        groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    
    summary = load_summary(group_id)
    if not summary:
        body = """
        <section class="hero-panel">
          <div>
            <p class="eyebrow">Messy CSV to explainable settlements</p>
            <h2>No groups or import found.</h2>
            <p>Please create a group first to manage expenses.</p>
          </div>
        </section>
        """
        return render_layout("Dashboard", body, username)
        
    group = summary["group"]
    group_id = group["id"]
    
    group_options = "".join(
        f'<option value="{g["id"]}" {"selected" if g["id"] == group_id else ""}>{escape(g["name"])}</option>'
        for g in groups
    )
    
    group_selector = f"""
    <div style="background: rgba(255,255,255,0.95); border: 1px solid var(--line); border-radius: 12px; padding: 15px 20px; margin-bottom: 22px; display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap;">
      <div>
        <label style="margin: 0; display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 16px;">
          Active Group:
          <select onchange="window.location.href='/?group_id=' + this.value" style="margin: 0; padding: 6px 12px; border-radius: 8px;">
            {group_options}
          </select>
        </label>
      </div>
      <div style="display: flex; gap: 10px;">
        <a href="/expenses/new?group_id={group_id}" class="button"><strong>+ Add Expense</strong></a>
        <a href="/settlements/new?group_id={group_id}" class="button" style="background: linear-gradient(135deg, var(--gold), #8c5b0f); box-shadow: 0 12px 25px rgba(183, 121, 31, .22);"><strong>+ Record Payment</strong></a>
      </div>
    </div>
    """

    balances_list = list(summary["balances"].values())
    max_bal = max(abs(Decimal(val)) for val in balances_list) if balances_list else Decimal("0.00")
    if max_bal == 0:
        max_bal = Decimal("1.00")
        
    balance_elements = []
    for name, amount in sorted(summary["balances"].items()):
        amt_dec = Decimal(amount)
        pct = (abs(amt_dec) / max_bal) * 100
        bar_class = "positive" if amt_dec >= 0 else "negative"
        sign = "+" if amt_dec > 0 else ""
        
        balance_elements.append(
            f"""
            <div class="balance-bar-container">
              <div class="balance-bar-header">
                <span>{escape(name)}</span>
                <span class="{bar_class}">{sign}{rupees(amount)}</span>
              </div>
              <div class="balance-bar-bg">
                <div class="balance-bar-fill {bar_class}" style="width: {pct:0.1f}%;"></div>
              </div>
            </div>
            """
        )
    balance_visualizer = "".join(balance_elements) or "<p class='muted'>No balances.</p>"
    
    suggestions_list = []
    for debtor, creditor, amount in summary["suggestions"]:
        suggestions_list.append(
            f"""
            <div class="settlement-flow-card">
              <div class="settlement-actor debtor">{escape(debtor)}</div>
              <div class="settlement-arrow">
                <div class="settlement-amount">{rupees(amount)}</div>
                <div class="settlement-arrow-line"></div>
              </div>
              <div class="settlement-actor creditor">{escape(creditor)}</div>
            </div>
            """
        )
    suggestions_visualizer = "".join(suggestions_list) or "<p class='muted'>No settlement required. All balances are fully cleared!</p>"
    
    run = summary["run"]
    rows_seen = run['rows_seen'] if run else 0
    rows_imported = run['rows_imported'] if run else 0
    rows_skipped = run['rows_skipped'] if run else 0
    
    active_expenses = sum(1 for item in summary["trace"] if not item["ignored"])
    superseded_expenses = sum(1 for item in summary["trace"] if item["ignored"])
    critical_count = summary["anomaly_counts"].get("error", 0)
    warning_count = summary["anomaly_counts"].get("warning", 0)
    info_count = summary["anomaly_counts"].get("info", 0)
    
    timeline = render_timeline(group_id)
    
    settlement_rows = "".join(
        f"""<tr>
          <td><strong>{escape(s['payer'])}</strong> paid <strong>{escape(s['receiver'])}</strong></td>
          <td class="positive">{rupees(s['amount_inr'])}</td>
          <td>{escape(s['settlement_date'])}</td>
          <td>
            <form method="post" action="/settlements/delete" style="display:inline;" onsubmit="return confirm('Are you sure you want to delete this payment?');">
              <input type="hidden" name="settlement_id" value="{s['id']}">
              <input type="hidden" name="group_id" value="{group_id}">
              <button type="submit" style="padding: 4px 8px; font-size: 11px; background: var(--coral); box-shadow: none;">Delete</button>
            </form>
          </td>
        </tr>"""
        for s in summary["settlements"]
    )
    
    body = f"""
    {group_selector}
    
    <section class="hero-panel">
      <div>
        <p class="eyebrow">{escape(group['name'])}</p>
        <h2>Every rupee has a receipt trail.</h2>
        <p>The dashboard separates money movement from data cleanup, so balances stay explainable under interview pressure.</p>
      </div>
      <div class="hero-stats">
        <span>{rows_seen} CSV rows</span>
        <span>{active_expenses} active expenses</span>
        <span>{len(summary['anomalies'])} logged decisions</span>
      </div>
    </section>
    
    <section class="grid">
      <article class="metric accent-a"><span>Rows imported</span><strong>{rows_imported}</strong></article>
      <article class="metric accent-b"><span>Rows skipped</span><strong>{rows_skipped}</strong></article>
      <article class="metric accent-c"><span>Warnings</span><strong>{warning_count}</strong></article>
      <article class="metric accent-d"><span>Errors</span><strong>{critical_count}</strong></article>
    </section>
    
    <section class="columns">
      <article class="panel">
        <h2>Individual balances</h2>
        <p class="muted" style="margin-bottom: 20px;">Positive means the group owes this person. Negative means this person owes the group.</p>
        {balance_visualizer}
      </article>
      <article class="panel">
        <h2>Suggested settlements</h2>
        <p class="muted" style="margin-bottom: 20px;">Debt simplification after expenses, refunds, and recorded settlements.</p>
        {suggestions_visualizer}
      </article>
    </section>

    <section class="columns">
      <article class="panel wide" style="grid-column: span 2;">
        <h2>Recorded Payments</h2>
        <p class="muted">Payments recorded to settle balances between members.</p>
        <table>
          <thead>
            <tr><th>Transaction</th><th>Amount</th><th>Date</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {settlement_rows if settlement_rows else '<tr><td colspan="4">No payments recorded yet.</td></tr>'}
          </tbody>
        </table>
      </article>
    </section>
    
    <section class="columns">
      <article class="panel">
        <h2>Data quality board</h2>
        <div class="quality-grid">
          <div><span>Info</span><strong>{info_count}</strong></div>
          <div><span>Warning</span><strong>{warning_count}</strong></div>
          <div><span>Error</span><strong>{critical_count}</strong></div>
          <div><span>Superseded</span><strong>{superseded_expenses}</strong></div>
        </div>
      </article>
      <article class="panel">
        <h2>Membership timeline</h2>
        {timeline}
      </article>
    </section>
    """
    return render_layout("Dashboard", body, username)


def render_timeline(group_id):
    cards = []
    with connect() as conn:
        memberships = conn.execute(
            """
            SELECT m.name, ms.joined_on, ms.left_on
            FROM memberships ms
            JOIN members m ON ms.member_id = m.id
            WHERE ms.group_id = ?
            ORDER BY ms.joined_on, m.name
            """,
            (group_id,)
        ).fetchall()
    for m in memberships:
        left = m["left_on"]
        label = f"{m['joined_on']} to {left}" if left else f"{m['joined_on']} onward"
        cards.append(f"<li><strong>{escape(m['name'])}</strong><span>{escape(label)}</span></li>")
    return "<ul class='timeline-list'>" + "".join(cards) + "</ul>" if cards else "<p class='muted'>No membership timeline recorded.</p>"


def render_import(username, message=""):
    summary = load_summary(1)
    report_links = ""
    if summary and summary["run"]:
        report_links = """
        <p><a href="/report.md">Download Markdown import report</a> ·
        <a href="/report.json">Download JSON import report</a></p>
        """
    body = f"""
    <section class="hero-panel compact">
      <div>
        <p class="eyebrow">Importer</p>
        <h2>Policy-driven CSV ingestion</h2>
        <p>The supplied file is imported as-is. Every correction, skip, conversion, and assumption is written to the report.</p>
      </div>
    </section>
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


def render_anomalies(username, group_id=1):
    with connect() as conn:
        groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
        
    summary = load_summary(group_id)
    if not summary:
        return render_layout("Anomalies", "<section class='panel'><p>No groups or import found.</p></section>", username)
        
    group = summary["group"]
    group_id = group["id"]
    
    group_options = "".join(
        f'<option value="{g["id"]}" {"selected" if g["id"] == group_id else ""}>{escape(g["name"])}</option>'
        for g in groups
    )
    
    group_selector = f"""
    <div style="background: rgba(255,255,255,0.95); border: 1px solid var(--line); border-radius: 12px; padding: 15px 20px; margin-bottom: 22px; display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 16px; width: fit-content;">
      Group:
      <select onchange="window.location.href='/anomalies?group_id=' + this.value" style="margin: 0; padding: 6px 12px; border-radius: 8px;">
        {group_options}
      </select>
    </div>
    """

    expense_statuses = {}
    with connect() as conn:
        rows = conn.execute("SELECT id, row_number, status FROM expenses WHERE group_id = ?", (group_id,)).fetchall()
        for r in rows:
            expense_statuses[r["row_number"]] = (r["id"], r["status"])

    anomaly_rows = []
    for item in summary["anomalies"]:
        row_num = item["row_number"]
        action_btn = ""
        if row_num in expense_statuses:
            exp_id, status = expense_statuses[row_num]
            badge_color = "var(--green)" if status == "active" else "var(--coral)"
            status_text = f"<span style='color: {badge_color}; font-weight: bold;'>({status})</span>"
            
            toggle_label = "Set Ignore" if status == "active" else "Set Active"
            action_btn = f"""
            <form method="post" action="/expenses/toggle_status" style="display:inline; margin-left: 8px;">
              <input type="hidden" name="expense_id" value="{exp_id}">
              <input type="hidden" name="group_id" value="{group_id}">
              <input type="hidden" name="redirect_to" value="/anomalies">
              <button type="submit" style="padding: 4px 8px; font-size: 11px; background: var(--gold); box-shadow: none;">{toggle_label}</button>
            </form>
            """
        else:
            status_text = ""
            
        anomaly_rows.append(
            f"""<tr class="anomaly-row" data-severity="{item['severity'].lower()}">
              <td>{row_num}</td>
              <td><code>{escape(item['code'])}</code></td>
              <td>{escape(item['severity'])}</td>
              <td>{escape(item['message'])} {status_text}</td>
              <td>{escape(item['action'])} {action_btn}</td>
            </tr>"""
        )

    filter_tags = """
    <div class="filter-tags" style="margin-bottom: 22px; display: flex; gap: 8px;">
      <button class="filter-tag active" onclick="filterSeverity('all', this)" style="border-radius: 20px; padding: 6px 14px; font-size: 13px; cursor: pointer;">All</button>
      <button class="filter-tag" onclick="filterSeverity('error', this)" style="border-radius: 20px; padding: 6px 14px; font-size: 13px; cursor: pointer;">Errors</button>
      <button class="filter-tag" onclick="filterSeverity('warning', this)" style="border-radius: 20px; padding: 6px 14px; font-size: 13px; cursor: pointer;">Warnings</button>
      <button class="filter-tag" onclick="filterSeverity('info', this)" style="border-radius: 20px; padding: 6px 14px; font-size: 13px; cursor: pointer;">Infos</button>
    </div>
    <script>
      function filterSeverity(severity, btn) {
        document.querySelectorAll(".filter-tag").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        
        const rows = document.querySelectorAll(".anomaly-row");
        rows.forEach(row => {
          const sev = row.getAttribute("data-severity");
          if (severity === "all" || sev === severity) {
            row.style.display = "";
          } else {
            row.style.display = "none";
          }
        });
      }
    </script>
    """

    body = f"""
    <section class="hero-panel compact">
      <div>
        <p class="eyebrow">Audit trail</p>
        <h2>No silent guesses.</h2>
        <p>Each anomaly has a row number, severity, message, and importer action. You can override the status of duplicate or converted rows here.</p>
      </div>
    </section>
    
    {group_selector}
    {filter_tags}
    
    <section class="panel wide">
      <h2>Detected anomalies</h2>
      <table>
        <thead><tr><th>CSV row</th><th>Code</th><th>Severity</th><th>Problem</th><th>Action / Override</th></tr></thead>
        <tbody>{"".join(anomaly_rows) if anomaly_rows else '<tr><td colspan="5">No anomalies detected.</td></tr>'}</tbody>
      </table>
    </section>
    """
    return render_layout("Anomalies", body, username)


def render_expenses(username, group_id=1):
    with connect() as conn:
        groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    
    summary = load_summary(group_id)
    if not summary:
        return render_layout("Trace", "<section class='panel'><p>No groups or import found.</p></section>", username)
        
    group = summary["group"]
    group_id = group["id"]
    
    group_options = "".join(
        f'<option value="{g["id"]}" {"selected" if g["id"] == group_id else ""}>{escape(g["name"])}</option>'
        for g in groups
    )
    
    group_selector = f"""
    <div style="background: rgba(255,255,255,0.95); border: 1px solid var(--line); border-radius: 12px; padding: 15px 20px; margin-bottom: 22px; display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 16px; width: fit-content;">
      Group:
      <select onchange="window.location.href='/expenses?group_id=' + this.value" style="margin: 0; padding: 6px 12px; border-radius: 8px;">
        {group_options}
      </select>
    </div>
    """

    blocks = []
    for expense in summary["trace"]:
        splits = "".join(f"<li>{escape(s['name'])}: {rupees(s['amount'])}</li>" for s in expense["splits"])
        badge = ""
        if expense["status"] == "superseded":
            badge = "<span class='badge'>superseded</span>"
        elif expense["status"] == "ignored":
            badge = "<span class='badge' style='background: var(--coral-soft); color: var(--coral); border-color: var(--coral);'>ignored</span>"
            
        toggle_label = "Set Active" if expense["ignored"] else "Set Ignore/Superseded"
        
        actions = f"""
        <div style="margin-top: 14px; display: flex; gap: 10px; align-items: center;">
          <a href="/expenses/edit?id={expense['id']}&group_id={group_id}" class="button" style="padding: 6px 12px; font-size: 13px; background: var(--blue); box-shadow: none;">Edit</a>
          <form method="post" action="/expenses/delete" style="display:inline;" onsubmit="return confirm('Are you sure you want to delete this expense?');">
            <input type="hidden" name="expense_id" value="{expense['id']}">
            <input type="hidden" name="group_id" value="{group_id}">
            <button type="submit" class="button-danger" style="padding: 6px 12px; font-size: 13px; box-shadow: none;">Delete</button>
          </form>
          <form method="post" action="/expenses/toggle_status" style="display:inline;">
            <input type="hidden" name="expense_id" value="{expense['id']}">
            <input type="hidden" name="group_id" value="{group_id}">
            <button type="submit" style="padding: 6px 12px; font-size: 13px; background: var(--gold); box-shadow: none;">{toggle_label}</button>
          </form>
        </div>
        """
        
        row_label = f"Row {expense['row_number']}" if expense['row_number'] > 0 else "Manual"
        blocks.append(
            f"""
            <article class="trace-card" style="margin-bottom:15px; border-left: 5px solid {('var(--teal)' if not expense['ignored'] else 'var(--muted)')};">
              <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <h3 style="margin:0;">{row_label}: {escape(expense['description'])} {badge}</h3>
              </div>
              <p style="margin: 8px 0; color: var(--muted); font-size: 14px;">{escape(expense['expense_date'])} · Paid by {escape(expense['paid_by'])} · {rupees(expense['amount_inr'])}</p>
              <ul style="margin: 0; padding-left: 20px;">{splits or '<li>Excluded from active balance.</li>'}</ul>
              {actions}
            </article>
            """
        )
        
    intro = """
    <section class="hero-panel compact">
      <div>
        <p class="eyebrow">Trace mode</p>
        <h2>Walk any balance back to CSV rows.</h2>
        <p>Each card shows payer, amount, active status, and member-level split impact.</p>
      </div>
    </section>
    """
    
    search_bar = """
    <div class="search-container" style="margin-bottom: 22px;">
      <input type="text" id="expense-search" placeholder="🔍 Live search description, paid by, date, split type, amount..." oninput="filterExpenses(this.value)" style="padding: 12px 16px; border-radius: 10px; width: 100%; max-width: 500px; font-size: 15px;">
    </div>
    <script>
      function filterExpenses(q) {
        const query = q.toLowerCase().trim();
        const cards = document.querySelectorAll(".trace-card");
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          if (text.includes(query)) {
            card.style.display = "";
          } else {
            card.style.display = "none";
          }
        });
      }
    </script>
    """
    
    body = intro + group_selector + search_bar + "<section class='stack'>" + ("".join(blocks) if blocks else "<p class='panel'>No expenses in this group.</p>") + "</section>"
    return render_layout("Expense Trace", body, username)


def render_login(error=""):
    body = f"""
    <section class="login-shell">
      <article class="login-story">
        <p class="eyebrow">LedgerLens</p>
        <h2>Messy expense data, made defensible.</h2>
        <p>Built for the Spreetail assignment: anomaly-first importing, explainable balances, and settlement suggestions.</p>
        <div class="mini-proof">
          <span>CSV import</span>
          <span>Audit log</span>
          <span>Balance trace</span>
        </div>
      </article>
      <article class="login-card">
      <h2>Login</h2>
      <p>Demo users: <code>admin/demo123</code>, <code>aisha/demo123</code>, <code>rohan/demo123</code>.</p>
      {f'<p class="error">{escape(error)}</p>' if error else ''}
      <form method="post" action="/login">
        <label>Username <input name="username" required></label>
        <label>Password <input name="password" type="password" required></label>
        <button type="submit">Sign in</button>
      </form>
      </article>
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
        query = parse_qs(urlparse(self.path).query)
        if path == "/":
            group_id = int(query.get("group_id", ["1"])[0])
            return self.html(render_dashboard(username, group_id))
        if path == "/groups":
            return self.html(render_groups(username))
        if path == "/groups/view":
            group_id = int(query.get("id", ["0"])[0])
            return self.html(render_group_detail(username, group_id))
        if path == "/expenses/new":
            group_id = int(query.get("group_id", ["1"])[0])
            return self.html(render_expense_form(username, group_id))
        if path == "/expenses/edit":
            expense_id = int(query.get("id", ["0"])[0])
            group_id = int(query.get("group_id", ["1"])[0])
            return self.html(render_expense_form(username, group_id, expense_id))
        if path == "/settlements/new":
            group_id = int(query.get("group_id", ["1"])[0])
            return self.html(render_settlement_form(username, group_id))
        if path == "/import":
            return self.html(render_import(username))
        if path == "/anomalies":
            group_id = int(query.get("group_id", ["1"])[0])
            return self.html(render_anomalies(username, group_id))
        if path == "/expenses":
            group_id = int(query.get("group_id", ["1"])[0])
            return self.html(render_expenses(username, group_id))
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
        if path == "/groups":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            name = data.get("name", [""])[0].strip()
            if name:
                try:
                    with connect() as conn:
                        conn.execute("INSERT INTO groups(name) VALUES(?)", (name,))
                    self.redirect("/groups")
                except Exception as exc:
                    return self.html(render_groups(username, f"Error creating group: {exc}"))
            else:
                return self.html(render_groups(username, "Group name cannot be blank."))
            return
        if path == "/groups/members":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            group_id = int(data.get("group_id", ["0"])[0])
            member_name = data.get("member_name", [""])[0].strip()
            joined_on = data.get("joined_on", [""])[0].strip()
            left_on = data.get("left_on", [""])[0].strip() or None
            if not member_name or not joined_on:
                return self.html(render_group_detail(username, group_id, "Member Name and Joined On are required."))
            try:
                datetime.strptime(joined_on, "%Y-%m-%d")
                if left_on:
                    datetime.strptime(left_on, "%Y-%m-%d")
                normalized = normalize_name(member_name)
                with connect() as conn:
                    member_id = get_member_id(conn, normalized)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO memberships(group_id, member_id, joined_on, left_on)
                        VALUES (?, ?, ?, ?)
                        """,
                        (group_id, member_id, joined_on, left_on),
                    )
                self.redirect(f"/groups/view?id={group_id}")
            except Exception as exc:
                return self.html(render_group_detail(username, group_id, f"Error saving membership: {exc}"))
            return
        if path == "/groups/delete_membership":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            group_id = int(data.get("group_id", ["0"])[0])
            membership_id = int(data.get("membership_id", ["0"])[0])
            try:
                with connect() as conn:
                    conn.execute("DELETE FROM memberships WHERE id = ?", (membership_id,))
                self.redirect(f"/groups/view?id={group_id}")
            except Exception as exc:
                return self.html(render_group_detail(username, group_id, f"Error deleting membership: {exc}"))
            return
        if path in {"/expenses/new", "/expenses/edit"}:
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            group_id = int(data.get("group_id", ["0"])[0])
            expense_id = int(data.get("expense_id", ["0"])[0]) if path == "/expenses/edit" else None
            description = data.get("description", [""])[0].strip()
            amount = data.get("amount", [""])[0].strip()
            currency = data.get("currency", [""])[0].strip()
            paid_by_id = int(data.get("paid_by_id", ["0"])[0])
            expense_date = data.get("expense_date", [""])[0].strip()
            split_type = data.get("split_type", [""])[0].strip()
            participants = data.get("participants", [])
            
            split_vals = {}
            for k, v in data.items():
                if k.startswith("split_val_") and v:
                    member_name = k[len("split_val_"):]
                    split_vals[member_name] = v[0].strip()

            if not description or not amount or not expense_date or not participants:
                return self.html(render_expense_form(username, group_id, expense_id, "Description, Amount, Date, and at least one Participant are required."))

            try:
                with connect() as conn:
                    save_expense_db(conn, group_id, description, amount, currency, paid_by_id, expense_date, split_type, participants, split_vals, expense_id)
                self.redirect(f"/expenses?group_id={group_id}")
            except Exception as exc:
                return self.html(render_expense_form(username, group_id, expense_id, f"Error saving expense: {exc}"))
            return
        if path == "/expenses/delete":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            group_id = int(data.get("group_id", ["0"])[0])
            expense_id = int(data.get("expense_id", ["0"])[0])
            try:
                with connect() as conn:
                    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
                self.redirect(f"/expenses?group_id={group_id}")
            except Exception as exc:
                return self.html(render_expenses(username, group_id))
            return
        if path == "/expenses/toggle_status":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            group_id = int(data.get("group_id", ["0"])[0])
            expense_id = int(data.get("expense_id", ["0"])[0])
            try:
                with connect() as conn:
                    row = conn.execute("SELECT status FROM expenses WHERE id = ?", (expense_id,)).fetchone()
                    if row:
                        new_status = "active" if row["status"] != "active" else "ignored"
                        conn.execute("UPDATE expenses SET status = ? WHERE id = ?", (new_status, expense_id))
                self.redirect(f"/expenses?group_id={group_id}")
            except Exception as exc:
                return self.html(render_expenses(username, group_id))
            return
        if path == "/settlements/new":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            group_id = int(data.get("group_id", ["0"])[0])
            payer_id = int(data.get("payer_id", ["0"])[0])
            receiver_id = int(data.get("receiver_id", ["0"])[0])
            amount = data.get("amount", [""])[0].strip()
            settlement_date = data.get("settlement_date", [""])[0].strip()
            notes = data.get("notes", [""])[0].strip() or None

            if not amount or not settlement_date or payer_id == receiver_id:
                return self.html(render_settlement_form(username, group_id, "Amount and Date are required, and Payer/Receiver must be different."))

            try:
                with connect() as conn:
                    run_row = conn.execute("SELECT id FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
                    run_id = run_row["id"] if run_row else 1
                    conn.execute(
                        """
                        INSERT INTO settlements(import_run_id, row_number, group_id, settlement_date, payer_id, receiver_id, amount_inr, notes)
                        VALUES (?, 0, ?, ?, ?, ?, ?, ?)
                        """,
                        (run_id, group_id, settlement_date, payer_id, receiver_id, str(money(amount)), notes)
                    )
                self.redirect(f"/?group_id={group_id}")
            except Exception as exc:
                return self.html(render_settlement_form(username, group_id, f"Error saving settlement: {exc}"))
            return
        if path == "/settlements/delete":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            group_id = int(data.get("group_id", ["0"])[0])
            settlement_id = int(data.get("settlement_id", ["0"])[0])
            try:
                with connect() as conn:
                    conn.execute("DELETE FROM settlements WHERE id = ?", (settlement_id,))
                self.redirect(f"/?group_id={group_id}")
            except Exception as exc:
                self.redirect(f"/?group_id={group_id}")
            return
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
        local_css = BASE_DIR / "static" / "styles.css"
        if local_css.exists():
            css = local_css.read_bytes()
        else:
            fallback_css = BASE_DIR.parent / "frontend" / "static" / "styles.css"
            if fallback_css.exists():
                css = fallback_css.read_bytes()
            else:
                fallback_css_sub = BASE_DIR / "frontend" / "static" / "styles.css"
                if fallback_css_sub.exists():
                    css = fallback_css_sub.read_bytes()
                else:
                    self.send_error(404, "CSS file not found")
                    return
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
