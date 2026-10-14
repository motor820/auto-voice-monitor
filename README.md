# Auto Voice Monitor / 汽车用户之声监测

一个可自行部署的汽车品牌用户评论监测项目：配置关注的品牌和汽车之家车系 ID，定期抓取口碑列表与详情页，清洗入本地 SQLite，生成带原帖链接、按主题去重的 Markdown 历史基线和增量日报。

> 当前仓库是私有原型，尚未正式开源。仅支持汽车之家口碑；规则筛选结果是待核实的用户反馈，不能当作故障率。未来公开前须再审查平台使用条款、抓取频率、引用范围、测试覆盖和许可。

## 5 分钟启动

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp config.example.json config.json
# 编辑 config.json 中的 brands / series ID
```

车系 ID 可从 `https://k.autohome.com.cn/<车系ID>/` 获取。首次抓取小批量试跑：

```bash
auto-voice --config config.json sync --brand hongqi --max-pages 2 --detail-limit 5
auto-voice --config config.json report --brand hongqi --kind baseline
```

日常增量运行：

```bash
auto-voice --config config.json sync --brand hongqi --max-pages 3 --detail-limit 20
auto-voice --config config.json report --brand hongqi --kind daily
```

`reports/` 下的 `.md` 是可分发产物。数据库、原始评论、配置和报告默认被 `.gitignore` 排除。`report` 同一品牌/日期/类型再次执行只返回原路径，不重复生成；日报只纳入尚未写入以往报告的反馈。

## 能做什么

- 多品牌、多车系配置；以真实子品牌为单位，避免把聚合入口与子品牌重复抓取。
- 列表接口增量抓取，详情页可选补全；保留原始 JSON、原文、原帖 URL 和平台发表时间。
- SQLite 唯一键去重；历史基线与后续日报共用持久状态。
- 保守的座舱主题规则：语音、车机、手机互联、导航、应用、高频控制、OTA、音频，以及可核查的正面体验。
- 报告区分本地采集时间与平台发表时间；同一主题展示独立评论数和原帖链接。

## 不做什么

- 不声称覆盖汽车之家全部历史。接口可能有分页窗口限制；`--full-history --max-pages N` 只是逐页回补上限。
- 不把评论自动认定为真实故障、普遍现象或当前软件版本仍存在的问题。
- 不在仓库中保存账号、Cookie、私人评论数据或平台原文全集。
- 不内置消息投递/公开托管；不同用户可通过自己的 cron、邮件或云盘适配器分发 Markdown。自动发送应在自己的环境中单独授权和配置。

进一步说明：[部署](docs/deployment.md) · [数据字段](docs/schema.md) · [方法与局限](docs/methodology.md) · [Agent skill](skills/auto-voice-monitor/SKILL.md)。
