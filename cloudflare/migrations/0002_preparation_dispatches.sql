-- Claim a date before the one outbound request, and never clear it on failure.
CREATE TABLE IF NOT EXISTS preparation_dispatches (
  date TEXT PRIMARY KEY,
  scheduled_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('claimed','accepted','failed','uncertain')),
  http_status INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
