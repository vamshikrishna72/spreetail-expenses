# Import Report

- Source file: `expenses_export.csv`
- Imported at: `2026-06-14T16:55:15Z`
- USD to INR rate: `83.00`
- Rows seen: `42`
- Rows imported: `39`
- Rows skipped: `3`

| Row | Code | Severity | Action | Message |
| --- | --- | --- | --- | --- |
| 6 | `duplicate_expense` | warning | Skipped later duplicate and kept first row. | Duplicate-looking row with same date, people, currency, and amount. |
| 7 | `amount_normalized` | info | Parsed to Decimal and stored a two-decimal INR value. | Amount had comma or whitespace formatting. |
| 9 | `name_normalized` | info | Used canonical member name. | Normalized payer &#x27;priya&#x27; to &#x27;Priya&#x27;. |
| 11 | `name_normalized` | info | Used canonical member name. | Normalized payer &#x27;Priya S&#x27; to &#x27;Priya&#x27;. |
| 13 | `missing_payer` | error | Skipped row; user must correct payer. | Expense has no paid_by value. |
| 14 | `settlement_not_expense` | warning | Recorded in settlements table and excluded from expense splits. | Row appears to be a payment/settlement, not an expense. |
| 15 | `percentage_total_not_100` | warning | Normalized percentages proportionally to 100%. | Percentages total 110%, not 100%. |
| 16 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 17 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 18 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 19 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 20 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 20 | `currency_converted` | info | Stored original currency and converted INR amount. | Converted USD to INR at 83.00. |
| 21 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 21 | `currency_converted` | info | Stored original currency and converted INR amount. | Converted USD to INR at 83.00. |
| 22 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 23 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 23 | `split_people_normalized` | info | Used canonical member names. | Normalized split participant names. |
| 23 | `currency_converted` | info | Stored original currency and converted INR amount. | Converted USD to INR at 83.00. |
| 24 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 25 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 24 | `near_duplicate_conflict` | warning | Superseded by later row with clearer note/context. | Possible duplicate has a conflicting amount. |
| 25 | `near_duplicate_conflict` | warning | Kept this row as active and marked earlier row superseded. | Possible duplicate has a conflicting amount. |
| 26 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 26 | `currency_converted` | info | Stored original currency and converted INR amount. | Converted USD to INR at 83.00. |
| 26 | `negative_amount` | warning | Treated as refund/credit reducing the original obligation. | Negative amount detected. |
| 27 | `date_normalized` | info | Stored normalized ISO date. | Year inferred as 2026 from surrounding trip rows. |
| 27 | `name_normalized` | info | Used canonical member name. | Normalized payer &#x27;rohan&#x27; to &#x27;Rohan&#x27;. |
| 28 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 28 | `missing_currency` | warning | Defaulted to INR because all nearby home expenses are INR. | Currency was blank. |
| 29 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 29 | `amount_normalized` | info | Parsed to Decimal and stored a two-decimal INR value. | Amount had comma or whitespace formatting. |
| 30 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 31 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 31 | `zero_amount` | warning | Skipped row because it has no financial effect. | Zero amount expense detected. |
| 32 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 32 | `percentage_total_not_100` | warning | Normalized percentages proportionally to 100%. | Percentages total 110%, not 100%. |
| 33 | `date_normalized` | info | Stored normalized ISO date. | Date normalized from DD/MM/YYYY format. |
| 34 | `date_normalized` | info | Stored normalized ISO date. | Ambiguous date 04/05/2026 treated as 2026-04-05 because surrounding rows describe April expenses. |
| 36 | `inactive_member_in_split` | warning | Removed inactive members and recalculated the split. | Inactive member(s) in split: Meera. |
| 42 | `split_details_on_equal` | warning | Ignored split_details because split_type is equal. | Equal split row also had split_details. |
