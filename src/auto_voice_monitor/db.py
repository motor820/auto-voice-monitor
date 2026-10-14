"""SQLite source-of-truth for self-hosted deployments."""
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  source_review_id TEXT NOT NULL,
  brand_id TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  series_id INTEGER NOT NULL,
  series_name TEXT NOT NULL,
  show_id TEXT,
  source_url TEXT,
  published_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  changed_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  review_text TEXT NOT NULL,
  sections_json TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  UNIQUE(source, source_review_id, series_id)
);
CREATE INDEX IF NOT EXISTS idx_reviews_brand_changed ON reviews(brand_id, changed_at);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY,
  review_id INTEGER NOT NULL REFERENCES reviews(id),
  theme_key TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK(sentiment IN ('issue','praise')),
  evidence TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  UNIQUE(review_id, theme_key, sentiment, evidence_hash)
);
CREATE INDEX IF NOT EXISTS idx_findings_theme ON findings(theme_key, sentiment);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY,
  brand_id TEXT NOT NULL,
  report_date TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('baseline','daily')),
  created_at TEXT NOT NULL,
  body_hash TEXT NOT NULL,
  path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'generated',
  UNIQUE(brand_id, report_date, kind)
);
CREATE TABLE IF NOT EXISTS reported_findings (
  report_id INTEGER NOT NULL REFERENCES reports(id),
  finding_id INTEGER NOT NULL REFERENCES findings(id),
  PRIMARY KEY(report_id, finding_id)
);
CREATE TABLE IF NOT EXISTS run_log (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  brand_id TEXT NOT NULL,
  series_id INTEGER,
  pages INTEGER NOT NULL DEFAULT 0,
  seen INTEGER NOT NULL DEFAULT 0,
  inserted INTEGER NOT NULL DEFAULT 0,
  changed INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
"""

def connect(path: str) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
