-- Only returned provider identifiers for deliberate same-date replacement.
-- No content, publication state, intents, hashes, versions or retry policy.
-- Existing history and scheduler claims are untouched. No data is dropped.
CREATE TABLE publication_ids (
  date TEXT NOT NULL,
  platform TEXT NOT NULL CHECK(platform IN ('instagram','facebook','tiktok')),
  kind TEXT NOT NULL CHECK(kind IN ('feed','story','photo')),
  object_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  PRIMARY KEY(platform, object_id)
);
CREATE INDEX publication_ids_date ON publication_ids(date, platform);
