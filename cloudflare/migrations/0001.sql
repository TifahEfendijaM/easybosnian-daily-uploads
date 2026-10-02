CREATE TABLE IF NOT EXISTS batches (
  date TEXT PRIMARY KEY,
  package_hash TEXT NOT NULL,
  package_json TEXT NOT NULL,
  reservation_keys TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT '{}',
  revision INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reservations (
  key TEXT PRIMARY KEY,
  batch_date TEXT NOT NULL REFERENCES batches(date)
);
CREATE INDEX IF NOT EXISTS reservations_batch ON reservations(batch_date);
CREATE TABLE IF NOT EXISTS generations (
  date TEXT NOT NULL REFERENCES batches(date),
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY(date,kind)
);
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES (1, '{"daily_enabled":false,"daily_authorized":true,"preparation_verified":false,"monitoring_ready":false,"active_since":""}');
CREATE TABLE IF NOT EXISTS alerts (date TEXT, stage TEXT, PRIMARY KEY(date, stage));
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  stage TEXT NOT NULL,
  error TEXT NOT NULL,
  publication TEXT NOT NULL,
  run_url TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
