# Scope and Anomaly Log

## Product Scope

LedgerLens solves the assignment for one group: `Spreetail Flatmates`.

Implemented:

- Login.
- Group and member records (with full CRUD UI for creating groups, members, and managing memberships).
- Membership windows for people joining/leaving (queried dynamically from the SQLite DB memberships table).
- Expense import from the supplied CSV.
- Equal, unequal, share, and percentage splits (both for imported CSV and manual expenses, calculated dynamically).
- USD to INR conversion.
- Settlement/payment records (with full CRUD UI to record and delete payments).
- Group balance summary.
- Individual traceability through the expense trace page.
- Import report with every detected anomaly and action.
- Dashboard-level data quality board and membership timeline (queried dynamically).
- Manual approval and override workflow (letting users toggle active/ignored status of rows on both the Anomalies and Trace pages to override importer decisions and recalculate balances in real-time).

Not implemented:

- Password reset.
- User-created exchange-rate tables.
- Multi-currency settlement suggestions.

## Membership Policy

- Aisha, Rohan, Priya: active from 2026-02-01.
- Meera: active 2026-02-01 through 2026-03-31.
- Dev: active 2026-02-08 through 2026-03-31 for trip-related expenses.
- Sam: active from 2026-04-08.
- Kabir: active only on 2026-03-11.

If a split includes a person outside their active window, the importer removes that person and recalculates the split.

## Anomaly Log

| CSV Row | Problem | Policy / Action |
| --- | --- | --- |
| 6 | Duplicate dinner at Marina Bites | Skipped later duplicate, kept first row. |
| 7 | Amount contains comma | Parsed with comma removed and stored as Decimal. |
| 9 | `priya` lowercase | Normalized to `Priya`. |
| 10 | Amount has three decimals | Rounded to paise using half-up rounding. |
| 11 | `Priya S` alias | Normalized to `Priya`. |
| 13 | Missing payer | Skipped row and recorded error. |
| 14 | Settlement logged in expense sheet | Stored in `settlements`, excluded from expense splits. |
| 15 | Percentage split totals 110% | Normalized percentages proportionally. |
| 16-18 | Date format `DD/MM/YYYY` | Parsed and stored as ISO date. |
| 20-21 | USD expenses | Converted to INR using documented rate `83.00`. |
| 23 | Kabir is not a flatmate | Added as temporary one-day participant. |
| 24-25 | Possible duplicate Thalassa dinner with different amount | Marked earlier row superseded, kept later row because its note identifies the conflict. |
| 26 | Negative USD amount | Treated as refund/credit reducing obligations. |
| 27 | `Mar 14` missing year and `rohan ` has trailing space | Inferred 2026 and normalized payer to `Rohan`. |
| 28 | Missing currency | Defaulted to INR because nearby home expenses are INR. |
| 29 | Amount has surrounding spaces | Trimmed and parsed. |
| 31 | Zero amount | Skipped because it has no financial effect. |
| 34 | Ambiguous date `04/05/2026` | Treated as 2026-04-05 and reported for review. |
| 36 | Meera appears after moving out | Removed Meera from split and recalculated. |
| 38 | Sam deposit looks like payment, but split type is equal | Imported as an expense because the CSV classifies it as equal; flagged through payer/split trace for review. |
| 42 | Equal split has share details | Ignored details because `split_type` is equal. |

## Database Schema

Tables:

- `users`: demo login users.
- `groups`: expense groups.
- `members`: people who can pay or owe money.
- `memberships`: join/leave date ranges per group.
- `import_runs`: one row per CSV import.
- `anomalies`: detected data problems and importer actions.
- `expenses`: normalized imported expenses.
- `expense_splits`: per-person owed amounts for each expense.
- `settlements`: payments between members.

The schema is relational and uses foreign keys between import runs, groups, members, expenses, splits, settlements, and anomalies.
