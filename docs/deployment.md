# 部署与运行

## 前提

- Python 3.10+；可访问汽车之家口碑列表与详情页。
- 本地可写目录。默认 SQLite，无需单独部署 PostgreSQL。
- 访问公开页面时遵守平台规则；配置 `request_interval_seconds` 控制间隔，建议先小批量验证。遇到登录墙、反爬或访问限制时停止，不绕过限制。

## 配置

复制 `config.example.json` 为 `config.json`，填写品牌 ID、品牌名、车系 ID 和车系名。`database`、`reports_dir` 相对于配置文件所在目录解析。`config.json` 被忽略，不会推送。

首次启动可从一两个车系、`--max-pages 2 --detail-limit 5` 试跑；确认列表字段、详情抓取、原帖 URL 后再扩大。增量抓取遇到一整页已知评论会停止；`--full-history` 才继续翻页，仍受 `--max-pages` 限制。详情页失败不会覆盖原有详情文本，列表原文仍会入库。

## 定时

示例：每天 08:00 抓取、08:20 生成日报（Linux crontab，按服务器本地时区；自行改绝对路径和品牌 ID）。

```cron
0 8 * * * cd /absolute/path/auto-voice-monitor && .venv/bin/auto-voice --config config.json sync --brand hongqi --max-pages 3 --detail-limit 20 >> data/cron.log 2>&1
20 8 * * * cd /absolute/path/auto-voice-monitor && .venv/bin/auto-voice --config config.json report --brand hongqi --kind daily >> data/cron.log 2>&1
```

注意：抓取失败后不应把“无新增”当成健康状态；日报会注明最近一次采集失败。生产环境建议把同步和报告串成一个 job：同步成功后才生成/投递，以免竞态或不完整数据。

## 备份、迁移与更新

停掉定时任务后备份 `data/reviews.sqlite`（若服务仍在写，使用 SQLite backup API，勿只复制主文件而漏掉 WAL）。报告可由库内数据重建，但已发布状态也在库中，迁移时须带数据库。升级代码前备份数据库；当前版本无自动 schema migration，新字段需显式迁移。

## 投递与隐私

报告文件保留车主原话短摘和原帖链接，不要默认公开托管。需要微信/飞书/邮件投递时，在自己的环境接入相应通知工具，并只发送给已授权接收者。公开发布前检查转载范围、个人信息与平台条款。
