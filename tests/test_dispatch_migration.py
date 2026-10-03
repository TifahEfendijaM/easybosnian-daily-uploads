import sqlite3
import unittest

from easybosnian.core import ROOT


class DispatchMigrationTests(unittest.TestCase):
    def test_migrations_preserve_settings_and_enforce_one_claim_per_date(self):
        database = sqlite3.connect(":memory:")
        migrations = sorted((ROOT / "cloudflare/migrations").glob("*.sql"))
        for migration in migrations:
            database.executescript(migration.read_text())
        database.execute("UPDATE settings SET value=? WHERE id=1", ('{"daily_enabled":true}',))
        database.execute("INSERT INTO preparation_dispatches(date,scheduled_at,status) VALUES(?,?,?)",
                         ("2026-10-04", "2026-10-04T03:00:00Z", "uncertain"))
        # Exercise the deployment helper's exact SQL splitting as well as rerunning
        # migrations: neither an existing claim nor publication settings may reset.
        for migration in migrations:
            for statement in migration.read_text().split(";"):
                if statement.strip():
                    database.executescript(statement)
        cursor = database.execute("INSERT OR IGNORE INTO preparation_dispatches(date,scheduled_at,status) VALUES(?,?,?)",
                                  ("2026-10-04", "2026-10-04T03:00:00Z", "claimed"))
        self.assertEqual(cursor.rowcount, 0)
        self.assertEqual(database.execute("SELECT status FROM preparation_dispatches").fetchone()[0], "uncertain")
        self.assertEqual(database.execute("SELECT value FROM settings WHERE id=1").fetchone()[0], '{"daily_enabled":true}')
        with self.assertRaises(sqlite3.IntegrityError):
            database.execute("INSERT INTO preparation_dispatches(date,scheduled_at,status) VALUES(?,?,?)",
                             ("2026-10-05", "2026-10-05T03:00:00Z", "retry"))
        database.close()
