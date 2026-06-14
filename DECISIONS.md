# Decision Log

## 0. Product Name and Positioning

Options considered:

- Generic shared expenses app.
- Splitwise-style clone.
- A product centered on explainability and anomaly handling.

Decision:

Name the app `LedgerLens` and position it around explainable cleanup of messy expense data.

Reason:

The assignment is not only about splitting expenses. The evaluation focuses on messy data, traceability, and explaining decisions live. The name and dashboard make that product thinking visible.

## 1. Stack

Options considered:

- Django + React.
- Flask.
- Standard-library Python web app with SQLite.

Decision:

Use standard-library Python with SQLite.

Reason:

The assignment rewards a working app that can be defended in a live session. The provided environment did not already include Django or Flask, and a dependency-heavy build would create avoidable setup risk. SQLite satisfies the relational database requirement, and the code is small enough to explain line by line.

## 2. Currency Conversion

Options considered:

- Treat USD as INR.
- Reject USD rows.
- Convert USD to INR with a documented fixed rate.

Decision:

Convert USD to INR at `1 USD = 83.00 INR`, while storing the original currency.

Reason:

Priya explicitly called out that a dollar cannot equal a rupee. A fixed documented rate is simple, repeatable, and easy to change later.

## 3. Duplicate Handling

Options considered:

- Delete duplicates silently.
- Keep all rows.
- Detect likely duplicates and record an action.

Decision:

Skip exact duplicate-looking rows. For conflicting near-duplicates, mark the earlier row as superseded and keep the later row when the note gives clearer context.

Reason:

Meera asked to approve changes, so silent deletion is wrong. The importer records every action in the anomaly report.

## 4. Membership Windows

Options considered:

- Charge whoever appears in the CSV.
- Hard-code only the original four flatmates.
- Store membership date ranges and validate splits against the expense date.

Decision:

Use membership windows.

Reason:

Sam should not owe March expenses, and Meera should not owe April expenses after moving out.

## 5. Negative Amounts

Options considered:

- Reject negative amounts.
- Treat them as normal expenses.
- Treat them as refunds/credits.

Decision:

Treat negative amounts as refunds/credits.

Reason:

The CSV row says `Parasailing refund`, so the amount should reduce the participants' obligation.

## 6. Percentage Totals Above 100

Options considered:

- Reject the row.
- Accept the percentages literally.
- Normalize percentages proportionally.

Decision:

Normalize percentages proportionally and record an anomaly.

Reason:

The row is likely intended as a percentage split, but the total is wrong. Normalization keeps the row usable while making the correction visible.

## 7. Missing Payer

Options considered:

- Guess payer from context.
- Split as unpaid.
- Skip and require correction.

Decision:

Skip the row and report an error.

Reason:

Guessing the payer would change balances silently and would be hard to defend.

## 8. Settlement Rows

Options considered:

- Import settlement rows as expenses.
- Ignore them.
- Store them separately as settlements.

Decision:

Store settlement rows in a separate `settlements` table.

Reason:

Payments between members affect balances differently from shared expenses.

## 9. Full CRUD Operations for Groups and Membership Windows

Options considered:
- Keep membership windows hardcoded in the Python script.
- Add dynamic DB management with complete UI CRUD views to create groups, members, and memberships.

Decision:
Implement full CRUD capability for groups, members, and memberships in the UI.

Reason:
To satisfy the constraint that membership can change over time and that groups can be created and managed dynamically, the app must let users manage groups and members' active periods in the UI rather than in the code itself.

## 10. Dynamic Expense splitting and Settlement creation in the UI

Options considered:
- Only allow importing expenses from the CSV.
- Add full UI capability to record, edit, and delete expenses and settlements dynamically.

Decision:
Add forms for new and edited expenses (supporting all split types dynamically) and settlements (with delete actions).

Reason:
The minimum product requirements specify that the app must let users create and manage expenses (supporting equal, unequal, share, percentage splits) and record payments/settlements. Doing this dynamically in the UI ensures full coverage of the app's requirements.

## 11. String Replacement vs Python f-string Templating for Javascript code

Options considered:
- Escape all curly braces in JavaScript f-strings (`{{` and `}}`).
- Use non-f-string templates and execute `.replace()` calls in Python.

Decision:
Use non-f-string template strings with placeholder tokens (e.g. `__TITLE__`, `__DESC_VAL__`) and perform `.replace()` operations.

Reason:
Using f-strings for HTML templates that contain heavy inline JavaScript functions leads to high syntax error risks, since JavaScript single curly braces collide with Python's format bracket syntax. Using token replacements completely isolates Python string formatting from JavaScript syntax.

## 12. Manual Status Toggling for Anomaly/Duplicate Override

Options considered:
- Only show anomaly lists as a static audit log.
- Add inline "Toggle Status" (Active/Ignored) buttons for duplicate or conflict rows on the Trace and Anomalies pages.

Decision:
Provide a "Set Ignore" / "Set Active" status toggle button on the Trace page and the Anomalies page.

Reason:
Meera explicitly requested to be able to approve anything the app deletes or changes. Toggling the status of imported rows dynamically adjusts their inclusion in balance calculations in real-time, allowing users to override automated importer decisions manually.

