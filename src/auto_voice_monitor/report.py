"""Conservative, traceable cockpit-experience screening and Markdown reports."""
import hashlib
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Precision-first rules. They produce candidates, not verified defects.
THEMES = {
    "voice-control": ("语音识别与车控", "issue", r"(语音|唤醒|指令|喊它).{0,35}(不准|不灵|听不懂|没反应|无法|不能|控制不了|误识别|说.{0,12}没)|(香氛).{0,35}(语音控制不了|没香氛)"),
    "infotainment-performance": ("车机性能与稳定性", "issue", r"(车机|中控屏|屏幕|系统).{0,32}(卡顿|卡死|迟钝|反应慢|启动慢|黑屏|死机|闪退|不流畅)|(卡顿|黑屏|死机|闪退).{0,25}(车机|中控屏|屏幕|系统|倒车影像)"),
    "phone-integration": ("手机互联与数字钥匙", "issue", r"(CarPlay|CarLife|HiCar|投屏|手机互联|车机互联|NFC钥匙|蓝牙).{0,35}(不支持|没有|无法|不能|断连|连不上|缺失|仅支持有线)|(不支持|没有|无法|不能).{0,35}(CarPlay|CarLife|HiCar|投屏|手机互联|无线互联|NFC钥匙)"),
    "navigation": ("导航与地图", "issue", r"(导航|地图|定位|路线).{0,30}(不准|偏差|延迟|滞后|没声音|不播报|逆行|错误|卡顿)|(隧道).{0,25}(定位不准|导航不准)"),
    "app-ecosystem": ("应用生态", "issue", r"(第三方应用|软件|APP|应用商城).{0,30}(太少|较少|不能安装|无法安装|不能下载|不支持|受限)|(不能|无法|不支持).{0,25}(下载|安装).{0,15}(软件|APP|应用)"),
    "control-discoverability": ("高频功能操作路径", "issue", r"(空调|香氛|座椅按摩|灯光|近光灯|菜单|触控|触摸).{0,35}(层级深|多级菜单|三级页面|操作繁琐|不方便|找不到|不灵敏|误触)|(多级菜单|三级页面).{0,20}(空调|灯光|按摩|香氛)"),
    "ota": ("OTA 与版本体验", "issue", r"(OTA|车机升级|系统更新|更新系统).{0,32}(太慢|失败|不及时|无响应|次数少|较慢)|(半年|一年).{0,30}(一次|没.{0,8}更新)"),
    "audio": ("音频与蓝牙", "issue", r"(蓝牙|音乐|音响|音频).{0,25}(断连|断联|卡顿|没声音|杂音|无法连接)|(蓝牙).{0,15}(连不上|不稳定)"),
    "voice-praise": ("语音体验亮点", "praise", r"(语音|唤醒|指令).{0,30}(灵敏|准确|响应快|好用|方便|听得懂|正确执行|精准响应)"),
    "screen-praise": ("车机与屏幕亮点", "praise", r"(车机|中控屏|屏幕|双屏).{0,40}(丝滑|流畅|不卡|没有任何卡顿|清晰|反应迅速|顺手|好用)"),
    "hud-praise": ("HUD 与跨屏导航亮点", "praise", r"(HUD|抬头显示|导航飞屏).{0,30}(实用|方便|清晰|不用低头|减少低头)"),
}
NEGATION = re.compile(r"不流畅|不准|不灵|不好用|不能|无法|卡顿|卡死|死机|黑屏|闪退|一般|较慢|偏慢|问题")
NO_PROBLEM = re.compile(r"没有(?:任何|出现|发生)?(?:.{0,4})(卡顿|黑屏|死机|闪退)|完全不卡顿|从不卡顿")

def sentences(text):
    seen = set()
    for raw in re.split(r"[。！？；;，,\n]+", text or ""):
        s = " ".join(raw.split()).strip(" ，、:")
        if 8 <= len(s) <= 260 and s not in seen:
            seen.add(s)
            yield s

def screen(review):
    results = []
    for sentence in sentences(review["review_text"]):
        for key, (label, sentiment, pattern) in THEMES.items():
            if sentiment == "issue" and NO_PROBLEM.search(sentence):
                continue
            if sentiment == "praise" and NEGATION.search(sentence) and not NO_PROBLEM.search(sentence):
                continue
            if re.search(pattern, sentence, re.I):
                results.append((key, label, sentiment, sentence))
    return results

def refresh_findings(conn, brand_id):
    rows = conn.execute("SELECT * FROM reviews WHERE brand_id=?", (brand_id,)).fetchall()
    inserted = 0
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for row in rows:
        for key, _, sentiment, evidence in screen(row):
            digest = hashlib.sha256(evidence.encode()).hexdigest()
            cur = conn.execute("INSERT OR IGNORE INTO findings(review_id,theme_key,sentiment,evidence,evidence_hash,detected_at) VALUES(?,?,?,?,?,?)",
                               (row["id"], key, sentiment, evidence, digest, now))
            inserted += cur.rowcount
    conn.commit()
    return len(rows), inserted

def render(conn, brand, report_date, kind, timezone):
    if kind == "daily":
        rows = conn.execute("SELECT f.*,r.series_name,r.source_review_id,r.source_url,r.published_at FROM findings f "
                            "JOIN reviews r ON r.id=f.review_id WHERE r.brand_id=? AND NOT EXISTS "
                            "(SELECT 1 FROM reported_findings x WHERE x.finding_id=f.id) ORDER BY f.id", (brand["id"],)).fetchall()
    else:
        rows = conn.execute("SELECT f.*,r.series_name,r.source_review_id,r.source_url,r.published_at FROM findings f "
                            "JOIN reviews r ON r.id=f.review_id WHERE r.brand_id=? ORDER BY f.id", (brand["id"],)).fetchall()
    groups = defaultdict(list)
    for row in rows:
        groups[(row["theme_key"], row["sentiment"])].append(row)
    total = conn.execute("SELECT count(*) FROM reviews WHERE brand_id=?", (brand["id"],)).fetchone()[0]
    series = conn.execute("SELECT count(distinct series_id) FROM reviews WHERE brand_id=?", (brand["id"],)).fetchone()[0]
    latest = conn.execute("SELECT max(last_seen_at) FROM reviews WHERE brand_id=?", (brand["id"],)).fetchone()[0]
    status = conn.execute("SELECT status,error FROM run_log WHERE brand_id=? ORDER BY id DESC LIMIT 1", (brand["id"],)).fetchone()
    lines = [f"# {brand['name']}智能座舱用户之声｜{report_date}", "",
             f"类型：{'历史基线' if kind == 'baseline' else '日报'}。评论库覆盖 {total} 条、{series} 个车系；最新扫描时间：{latest or '无'}。",
             "筛选为规则命中的候选反馈，不等于已验证缺陷；同一评论在不同主题可能重复计入。", ""]
    if status and status["status"] != "ok":
        lines += [f"**数据状态：最近一次采集失败（{status['error'] or status['status']}）；本报告可能不完整。**", ""]
    for sentiment, title in (("issue", "问题与机会点"), ("praise", "正面体验")):
        lines += [f"## {title}", ""]
        found = False
        for key, (label, tone, _) in THEMES.items():
            if tone != sentiment or (key, tone) not in groups:
                continue
            found = True
            items = groups[(key, tone)]
            unique_reviews = len({r["review_id"] for r in items})
            lines += [f"### {label}（{unique_reviews} 条独立评论）", ""]
            seen_review = set()
            for item in items:
                if item["review_id"] in seen_review:
                    continue
                seen_review.add(item["review_id"])
                link = f"[{item['source_review_id']}]({item['source_url']})" if item["source_url"] else item["source_review_id"]
                lines.append(f"- {item['series_name']}：{item['evidence']}（{link}）")
                if len(seen_review) >= 8:
                    break
            if unique_reviews > 8:
                lines.append(f"- 另有 {unique_reviews - 8} 条独立评论；可在数据库按主题追溯。")
            lines.append("")
        if not found:
            lines += ["本期无新增候选。", ""]
    lines += ["## 方法与限制", "", "- 来源：汽车之家车主口碑；链接取自原始 `showId`，不由评论编号拼接。",
              "- 同一评论按来源、评论 ID、车系 ID 去重；日报只纳入尚未写入以往报告的反馈。",
              "- `published_at` 为平台返回的发表时间；`first_seen_at`/`last_seen_at` 是本地采集时间，不能互换。",
              "- 规则筛选无法替代人工复核，跨车系数量受采集覆盖影响；重要问题应复现并核对车型和软件版本。",
              "- 历史基线与日报均为可重复生成的 Markdown；不含私人凭据。", ""]
    return "\n".join(lines), [r["id"] for r in rows]

def generate_report(conn, config, brand, kind="daily", report_date=None):
    tz = ZoneInfo(config.get("timezone", "Asia/Shanghai"))
    date = report_date or datetime.now(tz).date().isoformat()
    existing = conn.execute("SELECT path FROM reports WHERE brand_id=? AND report_date=? AND kind=?",
                            (brand["id"], date, kind)).fetchone()
    if existing:
        return existing["path"], False
    _, _ = refresh_findings(conn, brand["id"])
    body, ids = render(conn, brand, date, kind, tz)
    root = Path(config.get("reports_dir", "reports"))
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{brand['id']}-{kind}-{date}.md"
    path.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode()).hexdigest()
    cur = conn.execute("INSERT INTO reports(brand_id,report_date,kind,created_at,body_hash,path) VALUES(?,?,?,?,?,?)",
                       (brand["id"], date, kind, datetime.now(tz).isoformat(timespec="seconds"), digest, str(path)))
    conn.executemany("INSERT INTO reported_findings(report_id,finding_id) VALUES(?,?)", [(cur.lastrowid, x) for x in ids])
    conn.commit()
    return str(path), True
