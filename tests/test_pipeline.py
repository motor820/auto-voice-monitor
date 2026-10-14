import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auto_voice_monitor.collector import normalize, source_url, sync_series, upsert, valid_source_url
from auto_voice_monitor.db import connect
from auto_voice_monitor.report import generate_report, screen

BRAND = {"id": "hongqi", "name": "红旗"}
SERIES = {"id": 6913, "name": "红旗天工08"}

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(str(Path(self.tmp.name) / "reviews.sqlite"))
        self.cfg = {"timezone": "Asia/Shanghai", "reports_dir": str(Path(self.tmp.name) / "reports")}

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_show_id_is_not_review_id_and_upsert_is_idempotent(self):
        item = {"Koubeiid": 5905828, "showId": "01m0m8zrs26mwk0d9r68w00000", "posttime": "2026-08-22",
                "contents": [{"structuredname": "智能化", "content": "车上有香氛，但语音控制不了，系统说没香氛。"}]}
        row = normalize(item, BRAND, SERIES, {})
        self.assertIn("01m0m8zrs26mwk0d9r68w00000", row["source_url"])
        self.assertNotIn("5905828", row["source_url"])
        self.assertTrue(valid_source_url(row["source_url"]))
        self.assertFalse(valid_source_url("https://example.com/detail/view_x.html"))
        self.assertEqual(upsert(self.conn, row), "inserted")
        self.assertEqual(upsert(self.conn, row), "known")
        self.assertEqual(self.conn.execute("select count(*) from reviews").fetchone()[0], 1)

    def test_baseline_consumes_existing_and_daily_only_new_evidence(self):
        first = normalize({"Koubeiid": 1, "showId": "abc", "contents": [{"content": "车上有香氛，但是语音控制不了，系统说没有香氛。"}]}, BRAND, SERIES, {})
        self.assertEqual(upsert(self.conn, first), "inserted")
        path, created = generate_report(self.conn, self.cfg, BRAND, "baseline", "2026-10-13")
        self.assertTrue(created)
        self.assertIn("语音识别与车控", Path(path).read_text())
        daily, created = generate_report(self.conn, self.cfg, BRAND, "daily", "2026-10-14")
        self.assertTrue(created)
        self.assertIn("本期无新增候选", Path(daily).read_text())
        self.assertEqual(generate_report(self.conn, self.cfg, BRAND, "daily", "2026-10-14"), (daily, False))
        next_row = normalize({"Koubeiid": 2, "showId": "def", "contents": [{"content": "车机系统经常卡顿，打开导航反应很慢。"}]}, BRAND, SERIES, {})
        self.assertEqual(upsert(self.conn, next_row), "inserted")
        next_report, _ = generate_report(self.conn, self.cfg, BRAND, "daily", "2026-10-15")
        body = Path(next_report).read_text()
        self.assertIn("车机性能与稳定性", body)
        self.assertNotIn("没有香氛", body)

    def test_no_cadence_false_positive(self):
        hits = screen({"review_text": "2026款天工08车机丝滑流畅，没有任何卡顿，双屏独立系统很方便。"})
        self.assertFalse(any(sentiment == "issue" for _, _, sentiment, _ in hits))

    def test_history_detail_backfill_skips_already_enriched_rows(self):
        items = [
            {"Koubeiid": 1, "showId": "abc", "contents": [{"content": "车机操作流畅，语音控制方便。"}]},
            {"Koubeiid": 2, "showId": "def", "contents": [{"content": "香氛不能通过语音控制。"}]},
        ]
        upsert(self.conn, normalize(items[0], BRAND, SERIES, {"intelligence": "车机操作流畅"}))
        upsert(self.conn, normalize(items[1], BRAND, SERIES, {}))
        with patch("auto_voice_monitor.collector.fetch_page", return_value={"list": items, "pagecount": 1}), \
             patch("auto_voice_monitor.collector.fetch_sections", return_value={"intelligence": "香氛不能通过语音控制"}) as fetch, \
             patch("auto_voice_monitor.collector.time.sleep"):
            result = sync_series(self.conn, object(), BRAND, SERIES, max_pages=1, full_history=True, detail_limit=1)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result["changed"], 1)
        self.assertEqual(self.conn.execute("select count(*) from reviews where sections_json != '{}' ").fetchone()[0], 2)

if __name__ == "__main__":
    unittest.main()
