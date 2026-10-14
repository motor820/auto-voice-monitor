import argparse
import json
from pathlib import Path

import requests

from .collector import sync_series
from .db import connect
from .report import generate_report

def load_config(path):
    file = Path(path).resolve()
    config = json.loads(file.read_text(encoding="utf-8"))
    if not config.get("brands"):
        raise ValueError("config.brands must contain at least one brand")
    for key in ("database", "reports_dir"):
        config[key] = str((file.parent / config[key]).resolve())
    return config

def main(argv=None):
    parser = argparse.ArgumentParser(prog="auto-voice")
    parser.add_argument("--config", default="config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="collect and upsert owner reviews")
    sync.add_argument("--brand", help="configured brand id; omitted means all")
    sync.add_argument("--max-pages", type=int, default=3)
    sync.add_argument("--full-history", action="store_true")
    sync.add_argument("--detail-limit", type=int, default=20)
    report = sub.add_parser("report", help="generate a baseline or incremental Markdown report")
    report.add_argument("--brand", required=True)
    report.add_argument("--kind", choices=["baseline", "daily"], default="daily")
    report.add_argument("--date")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    conn = connect(cfg["database"])
    brands = [b for b in cfg["brands"] if not getattr(args, "brand", None) or b["id"] == args.brand]
    if not brands:
        parser.error("brand not found in config")
    if args.command == "sync":
        if args.max_pages < 1 or args.detail_limit < 0:
            parser.error("max-pages must be >=1 and detail-limit >=0")
        session = requests.Session()
        for brand in brands:
            for series in brand["series"]:
                result = sync_series(conn, session, brand, series, max_pages=args.max_pages,
                                     full_history=args.full_history, detail_limit=args.detail_limit,
                                     interval=float(cfg.get("request_interval_seconds", 1.5)))
                print(json.dumps({"brand": brand["id"], "series": series["name"], **result}, ensure_ascii=False))
    else:
        path, created = generate_report(conn, cfg, brands[0], args.kind, args.date)
        print(json.dumps({"path": path, "created": created}, ensure_ascii=False))

if __name__ == "__main__":
    main()
