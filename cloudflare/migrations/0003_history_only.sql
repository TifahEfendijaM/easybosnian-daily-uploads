-- Preserve content and cron claims, discard publication/reservation machinery.
CREATE TABLE IF NOT EXISTS history (
  date TEXT PRIMARY KEY,
  theme_json TEXT NOT NULL,
  words_json TEXT NOT NULL,
  content_json TEXT NOT NULL
);
-- Explicit user-authorized exception: discard the rejected October 3 batch.
INSERT OR IGNORE INTO history(date,theme_json,words_json,content_json)
SELECT date,json_extract(package_json,'$.theme'),json_extract(package_json,'$.words'),package_json
FROM batches
WHERE NOT (date='2026-10-03' AND package_hash='759bd137b4b4ed33a37a7efdda952925ef345e8c31aa40c78f4754980e493f7a');
DELETE FROM preparation_dispatches WHERE date='2026-10-03';
DROP TABLE IF EXISTS reservations;
DROP TABLE IF EXISTS generations;
DROP TABLE IF EXISTS batches;
DROP TABLE IF EXISTS alerts;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS settings;
