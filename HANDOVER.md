# 每日投资简报 · 交接文档（HANDOVER）

本仓库是一个全自动的每日投资简报系统：每天早上 8:00（北京时间）由 GitHub Actions 生成简报、部署网站、推送微信。本文档供接管者（人或 AI）快速理解与维护。

## 架构总览

```
GitHub Actions（每天 08:00 CST / 00:00 UTC）
  └─ scripts/daily_briefing.py gen     抓行情 → 实算指标 → 写简报 md + 表格图 → 提交 main
  └─ npm run build                     React+Vite 构建到 dist/
  └─ 部署步骤                           dist/ 内容替换 gh-pages 分支根目录
  └─ scripts/daily_briefing.py notify  验证线上 → Server酱推送微信
```

- **线上站点**：https://lixiayang1.github.io/daily-market-briefing/ （GitHub Pages，来自 `gh-pages` 分支）
- **定时入口**：`.github/workflows/daily.yml`（cron `0 0 * * *`，可 workflow_dispatch 手动触发）

## 分支约定（重要）

| 分支 | 内容 |
|---|---|
| `main` | 全部源代码：React 站点（`src/`）、简报数据（`public/briefings/`：YYYY-MM-DD.md + index.json + img/ + .state.json）、生成脚本（`scripts/`）、CI（`.github/workflows/`） |
| `gh-pages` | 仅构建产物，**根目录直接是** `index.html`、`assets/`、`briefings/`、`.nojekyll`（绝不能出现 dist 子目录），由 CI 自动维护，不要手工编辑 |

## 数据口径与来源

- 数据截至各市场**最近一个交易日收盘**；盘中（15:00 CST 前）会剔除港/A 股当日未完成 K 线。
- 美股指数/个股：Yahoo Finance（query1/query2 互备）；港股、A股、个股：腾讯行情；A股指数备用：东方财富（中证消费50 931139 固定走东财）。
- 实算指标：最新收盘、当日涨跌、20 交易日涨跌、相对强弱（美股对 S&P 500、港股对恒指、A股对中证A500，差值 pct）、MA250 偏离（年线）、个股 MA50/MA200 偏离。
- 估值项：高收益债 OAS（FRED BAMLH0A0HYM2）、Shiller CAPE（multpl.com）每次尽力刷新；Fear & Greed（CNN 反爬）与远期 PE（FactSet）自动沿用上期并在"注"里标注"未刷新"。
- 任何单市场有新数据即正常发布；三个市场都无新收盘（周末等）→ 静默跳过，不发推送，仅做网站健康检查。

## 密钥与凭据（不在仓库中）

| 凭据 | 位置 | 说明 |
|---|---|---|
| `SCT_KEYS` | GitHub 仓库 Settings → Secrets → Actions | Server酱 SendKey，逗号分隔多个；新增订阅者在此追加 |
| `GITHUB_TOKEN` | CI 自动注入 | 用于推送 gh-pages，workflow 已声明 `permissions: contents: write` |

Secrets 无法被读出，接管时如需更换推送对象，直接覆盖更新 `SCT_KEYS` 即可。

## 常见维护操作

- **手动触发一次**：Actions → daily-briefing → Run workflow（ref: main）。
- **暂停推送**：仓库 Settings → Actions → 禁用 workflow，或把 cron 注释掉。
- **修改指数池/文案模板**：改 `scripts/daily_briefing.py` 里的 `INDEX_ROWS` 与解读函数（`us_commentary` / `cn_commentary` / `nvda_commentary` / `abnb_commentary` / `portfolio_action`）。
- **本地调试**：`BRIEF_DIR=/tmp/test FORCE=1 DRY_RUN=1 python scripts/daily_briefing.py gen`（只写文件不提交）。
- **排障**：Actions 运行日志；任务失败会自动向所有 SCT_KEYS 推送"异常"提醒。

## 已知取舍

- 解读文字为规则化模板生成（非大模型写作）；如需 AI 深度解读版，可在 gen 阶段接入模型 API。
- GitHub 定时任务可能有数分钟延迟，属正常现象。

—— 本系统最初由 Kimi 搭建（2026-10），以上为市场分析工具，不构成投资建议。
