import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import app


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = app.DB_PATH
        self.original_data_dir = app.DATA_DIR
        self.original_report_dir = app.REPORT_DIR
        app.DATA_DIR = Path(self.tempdir.name) / "data"
        app.REPORT_DIR = Path(self.tempdir.name) / "reports"
        app.DB_PATH = app.DATA_DIR / "test.sqlite3"

    def tearDown(self):
        app.DB_PATH = self.original_db_path
        app.DATA_DIR = self.original_data_dir
        app.REPORT_DIR = self.original_report_dir
        self.tempdir.cleanup()

    def test_import_detects_messy_csv_and_balances(self):
        report = app.import_csv(app.CSV_PATH)
        self.assertEqual(report["rows_seen"], 42)
        self.assertGreaterEqual(len(report["anomalies"]), 20)
        codes = {item["code"] for item in report["anomalies"]}
        expected_codes = {
            "duplicate_expense",
            "amount_normalized",
            "name_normalized",
            "missing_payer",
            "settlement_not_expense",
            "percentage_total_not_100",
            "currency_converted",
            "near_duplicate_conflict",
            "negative_amount",
            "missing_currency",
            "zero_amount",
            "inactive_member_in_split",
            "split_details_on_equal",
        }
        self.assertTrue(expected_codes.issubset(codes))

        summary = app.load_summary()
        total = sum(summary["balances"].values(), Decimal("0"))
        self.assertEqual(app.money(total), Decimal("0.00"))
        self.assertTrue(summary["suggestions"])

    def test_crud_and_status_toggles(self):
        app.init_db()
        with app.connect() as conn:
            conn.execute("INSERT INTO groups(name) VALUES('New Test Group')")
            group_id = conn.execute("SELECT id FROM groups WHERE name='New Test Group'").fetchone()["id"]
            bob_id = app.get_member_id(conn, "Bob")
            aisha_id = app.get_member_id(conn, "Aisha")
            
            conn.execute("INSERT INTO memberships(group_id, member_id, joined_on, left_on) VALUES (?, ?, '2026-06-01', NULL)", (group_id, bob_id))
            conn.execute("INSERT INTO memberships(group_id, member_id, joined_on, left_on) VALUES (?, ?, '2026-06-01', NULL)", (group_id, aisha_id))
            
            app.save_expense_db(
                conn, 
                group_id, 
                "Pizza Party", 
                "100.00", 
                "INR", 
                bob_id, 
                "2026-06-05", 
                "equal", 
                ["Bob", "Aisha"], 
                {}
            )
            
        summary = app.load_summary(group_id)
        self.assertEqual(summary["balances"]["Bob"], Decimal("50.00"))
        self.assertEqual(summary["balances"]["Aisha"], Decimal("-50.00"))
        
        with app.connect() as conn:
            app.save_expense_db(
                conn,
                group_id,
                "Drinks",
                "100.00",
                "INR",
                aisha_id,
                "2026-06-06",
                "percentage",
                ["Bob", "Aisha"],
                {"Bob": "70", "Aisha": "30"}
            )
            
        summary = app.load_summary(group_id)
        self.assertEqual(summary["balances"]["Bob"], Decimal("-20.00"))
        self.assertEqual(summary["balances"]["Aisha"], Decimal("20.00"))
        
        with app.connect() as conn:
            conn.execute(
                """
                INSERT INTO settlements(import_run_id, row_number, group_id, settlement_date, payer_id, receiver_id, amount_inr, notes)
                VALUES (1, 0, ?, '2026-06-07', ?, ?, '20.00', 'Clear debt')
                """,
                (group_id, bob_id, aisha_id)
            )
            
        summary = app.load_summary(group_id)
        self.assertEqual(summary["balances"]["Bob"], Decimal("0.00"))
        self.assertEqual(summary["balances"]["Aisha"], Decimal("0.00"))
        
        pizza_expense_id = summary["trace"][0]["id"]
        with app.connect() as conn:
            conn.execute("UPDATE expenses SET status = 'ignored' WHERE id = ?", (pizza_expense_id,))
            
        summary = app.load_summary(group_id)
        self.assertEqual(summary["balances"]["Bob"], Decimal("-50.00"))
        self.assertEqual(summary["balances"]["Aisha"], Decimal("50.00"))


if __name__ == "__main__":
    unittest.main()
