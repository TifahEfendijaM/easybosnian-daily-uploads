import json
import sqlite3
import unittest
from easybosnian.core import ROOT


class MigrationTests(unittest.TestCase):
    def test_content_carried_over_rejected_today_dropped_and_other_cron_claim_preserved(self):
        db=sqlite3.connect(':memory:');db.execute('PRAGMA foreign_keys=ON')
        for name in ['0001.sql','0002_preparation_dispatches.sql']:db.executescript((ROOT/'cloudflare/migrations'/name).read_text())
        content={'theme':{'name':'old theme','equivalence_keys':['theme']},'words':[{'lemma':'word','equivalence_keys':['alias']}],'cards':['reviewed']}
        rejected='759bd137b4b4ed33a37a7efdda952925ef345e8c31aa40c78f4754980e493f7a'
        for date,hash_value in [('2026-10-01','other'),('2026-10-03',rejected)]:
            db.execute('INSERT INTO batches(date,package_hash,package_json,reservation_keys,state) VALUES(?,?,?,?,?)',(date,hash_value,json.dumps(content),'[]','{"publish_intent":true,"verified":true}'))
            db.execute('INSERT INTO reservations VALUES(?,?)',('word:'+date,date))
            db.execute('INSERT INTO generations VALUES(?,?,?)',(date,'quiz','done'))
            db.execute('INSERT INTO preparation_dispatches(date,scheduled_at,status) VALUES(?,?,?)',(date,date+'T10:00:00Z','accepted'))
        db.executescript((ROOT/'cloudflare/migrations/0003_history_only.sql').read_text())
        self.assertEqual(db.execute('SELECT date FROM history').fetchall(),[('2026-10-01',)])
        self.assertEqual(json.loads(db.execute('SELECT content_json FROM history').fetchone()[0]),content)
        self.assertEqual(db.execute('SELECT date FROM preparation_dispatches').fetchall(),[('2026-10-01',)])
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse(tables & {'batches','reservations','generations','settings','alerts','events'})
        db.close()
