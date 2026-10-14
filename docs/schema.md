# SQLite 数据契约

完整 DDL 在 `src/auto_voice_monitor/db.py`，此处说明关键字段。

| 表 | 作用 | 关键字段/约束 |
|---|---|---|
| `reviews` | 原始评论与清洗正文 | `UNIQUE(source, source_review_id, series_id)`；`show_id` 单独用于原帖 URL，**不是** `source_review_id`；`published_at` 为平台时间，`first_seen_at/last_seen_at/changed_at` 为本地时间；`content_hash` 检测变化；`raw_json`、`sections_json` 可追溯 |
| `findings` | 按句抽取的候选问题/亮点 | `review_id`、`theme_key`、`sentiment`、`evidence`、`evidence_hash`；同评论同主题同句唯一 |
| `reports` | 已生成的 Markdown 报告 | `UNIQUE(brand_id, report_date, kind)`；`kind=baseline/daily`、`body_hash`、`path`、`status` |
| `reported_findings` | 已写入报告的反馈记录 | `(report_id, finding_id)` 主键；日报只取未出现在此表的反馈 |
| `run_log` | 抓取运行结果 | `status`、页数、见到/新增/变化数量、错误；供日报标记数据健康状态 |

时间均保留 ISO 8601 格式；报告日期使用配置中的时区。增量去重依赖同一 SQLite 数据库，删除库将丢失历史去重状态。
