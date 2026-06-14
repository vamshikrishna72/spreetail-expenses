# Decision Log

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

