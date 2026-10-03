-- Separate content date from batch identity; no publication states or retry flags.
-- Legacy creation times use actual review timestamps when available, else midnight UTC.
CREATE TABLE history_next (
  batch_id TEXT PRIMARY KEY,
  date TEXT NOT NULL,
  created_at TEXT NOT NULL,
  theme_json TEXT NOT NULL,
  words_json TEXT NOT NULL,
  content_json TEXT NOT NULL
);
INSERT INTO history_next(rowid,batch_id,date,created_at,theme_json,words_json,content_json)
SELECT rowid,'legacy-'||date,date,
       COALESCE(strftime('%Y-%m-%dT%H:%M:%fZ',json_extract(content_json,'$.private_review.reviewed_at')),date||'T00:00:00.000Z'),
       theme_json,words_json,json_set(content_json,'$.batch_id','legacy-'||date)
FROM history;
DROP TABLE history;
ALTER TABLE history_next RENAME TO history;
CREATE INDEX history_created ON history(created_at);
CREATE INDEX history_date ON history(date);

CREATE TABLE publication_ids_next (
  batch_id TEXT NOT NULL,
  date TEXT NOT NULL,
  platform TEXT NOT NULL CHECK(platform IN ('instagram','facebook','tiktok')),
  kind TEXT NOT NULL CHECK(kind IN ('feed','story','photo')),
  object_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  PRIMARY KEY(platform,object_id)
);
-- Preserve insertion order and every known identifier, including orphan/older IDs.
-- Only the final recorded feed and following Stories in a legacy bucket are cleanup targets.
INSERT INTO publication_ids_next(rowid,batch_id,date,platform,kind,object_id,account_id)
SELECT rowid,'legacy-'||date,date,platform,kind,object_id,account_id FROM publication_ids;
DROP TABLE publication_ids;
ALTER TABLE publication_ids_next RENAME TO publication_ids;
CREATE INDEX publication_ids_batch ON publication_ids(batch_id,platform);
CREATE INDEX publication_ids_date ON publication_ids(date,platform);
-- preparation_dispatches and public KV URLs are unchanged. No content/IDs are dropped.
