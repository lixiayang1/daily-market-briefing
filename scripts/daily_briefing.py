#!/usr/bin/env python3
"""每日投资简报云端生成器（GitHub Actions 版）。

用法:
  python scripts/daily_briefing.py gen     # 抓数据、写简报、生成表格图、提交 main
  python scripts/daily_briefing.py notify  # 验证线上部署并推送 Server酱

环境变量:
  SCT_KEYS        Server酱 SendKey，多个用英文逗号分隔（必填，仅 notify 与失败提醒用）
  DRY_RUN=1       只写文件，不提交不推送（本地调试用）
  SITE_BASE       默认 https://lixiayang1.github.io/daily-market-briefing
"""
import csv, io, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

SITE = os.environ.get("SITE_BASE", "https://lixiayang1.github.io/daily-market-briefing")
CST = timezone(timedelta(hours=8))
TODAY = datetime.now(CST).date()
TODAY_S = TODAY.isoformat()
TITLE_DATE = f"{TODAY.year}年{TODAY.month}月{TODAY.day}日"
BRIEF_DIR = os.environ.get("BRIEF_DIR", "public/briefings")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# ---------- 数据抓取 ----------

def http_get(url, timeout=25, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8-sig", "replace")
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    raise last

def fetch_yahoo(sym, days=1100):
    end = int(time.time()) + 86400
    start = end - days * 86400
    last = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            d = json.loads(http_get(
                f"https://{host}/v8/finance/chart/{sym}"
                f"?period1={start}&period2={end}&interval=1d"))
            break
        except Exception as e:
            last = e
    else:
        raise last
    r = d["chart"]["result"][0]
    off = r["meta"].get("gmtoffset", 0)
    out = {}
    for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]):
        if c is not None:
            out[datetime.fromtimestamp(t + off, timezone.utc).date().isoformat()] = c
    return sorted(out.items())

def fetch_tencent(code, n=600):
    d = json.loads(http_get(
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq"))
    node = d["data"][code]
    rows = node.get("qfqday") or node.get("day")
    if not rows:
        raise RuntimeError(f"empty tencent series: {code}")
    return [(r[0], float(r[2])) for r in rows]

def fetch_eastmoney(secid, years=3):
    beg = (TODAY - timedelta(days=years * 365)).strftime("%Y%m%d")
    last = None
    for host in ("push2his.eastmoney.com", "push2his1.eastmoney.com",
                 "push2his2.eastmoney.com", "push2his3.eastmoney.com"):
        try:
            d = json.loads(http_get(
                f"https://{host}/api/qt/stock/kline/get?secid={secid}"
                f"&fields1=f1,f2,f3&fields2=f51,f53&klt=101&fqt=0&beg={beg}&end=20500101"))
            rows = (d.get("data") or {}).get("klines") or []
            if rows:
                return [(r.split(",")[0], float(r.split(",")[1])) for r in rows]
            last = RuntimeError(f"empty eastmoney series: {secid}")
        except Exception as e:
            last = e
    raise last

def drop_intraday(series, mkt):
    """港股/A股在盘中会返回当日未完成K线：15:00(CST)收盘前的当日 bar 一律剔除。"""
    if mkt in ("港", "A") and datetime.now(CST).hour < 15 and series and series[-1][0] == TODAY_S:
        return series[:-1]
    return series

def metrics(series):
    vals = [v for _, v in series]
    last = vals[-1]
    m = {"date": series[-1][0], "close": last,
         "day": (last / vals[-2] - 1) * 100,
         "chg20": (last / vals[-21] - 1) * 100,
         "ma250": sum(vals[-250:]) / min(250, len(vals))}
    m["dev250"] = (last / m["ma250"] - 1) * 100
    for n in (50, 200):
        m[f"ma{n}"] = sum(vals[-n:]) / n
        m[f"dev{n}"] = (last / m[f"ma{n}"] - 1) * 100
    return m

def collect():
    src = {}
    m = {}
    mkt_of = {"SPX": "美", "DJI": "美", "NDX": "美", "NVDA": "美", "ABNB": "美",
              "HSI": "港", "HSTECH": "港", "A500": "A", "CSI500": "A",
              "STAR50": "A", "CHINEXT": "A", "CONS50": "A"}
    for k, s in {"SPX": "^GSPC", "DJI": "^DJI", "NDX": "^NDX"}.items():
        m[k] = metrics(drop_intraday(fetch_yahoo(s), mkt_of[k])); src[k] = "Yahoo Finance"
    for k, c in {"NVDA": "usNVDA.OQ", "ABNB": "usABNB.OQ", "HSI": "hkHSI",
                 "HSTECH": "hkHSTECH", "A500": "sh000510", "CSI500": "sh000905",
                 "STAR50": "sh000688", "CHINEXT": "sz399006"}.items():
        try:
            m[k] = metrics(drop_intraday(fetch_tencent(c), mkt_of[k])); src[k] = "腾讯行情"
        except Exception as e:
            print(f"tencent {k} failed: {e!r}")
    em_backup = {"A500": "1.000510", "CSI500": "1.000905", "STAR50": "1.000688",
                 "CHINEXT": "0.399006"}
    for k, secid in em_backup.items():  # 腾讯缺失的 A 股指数用东财补齐
        if k not in m:
            m[k] = metrics(drop_intraday(fetch_eastmoney(secid), "A")); src[k] = "东方财富"
    try:
        m["CONS50"] = metrics(drop_intraday(fetch_tencent("sh931139"), "A")); src["CONS50"] = "腾讯行情"
    except Exception:
        m["CONS50"] = metrics(drop_intraday(fetch_eastmoney("2.931139"), "A")); src["CONS50"] = "东方财富"
    need = set(mkt_of)
    missing = need - set(m)
    if missing:
        raise RuntimeError(f"数据缺失: {sorted(missing)}")
    return m, src

# ---------- 估值与拥挤度（尽力刷新，失败沿用上一期） ----------

def parse_prev(prev_md, pattern):
    mt = re.search(pattern, prev_md)
    return mt.groups() if mt else None

def refresh_valuations(prev_md):
    v = {}
    try:  # 高收益债利差 FRED
        beg = (TODAY - timedelta(days=10)).isoformat()
        rows = list(csv.reader(io.StringIO(http_get(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd={beg}"))))
        rows = [r for r in rows[1:] if len(r) > 1 and r[1] not in ("", ".")]
        v["oas"] = (f"{float(rows[-1][1]):.2f}", rows[-1][0], True)
    except Exception:
        p = parse_prev(prev_md, r"高收益债OAS约([\d.]+)%（FRED/ICE BofA，([^，）]*)")
        v["oas"] = (p[0], p[1], False) if p else ("3.2", "上期", False)
    try:  # Shiller CAPE multpl
        mt = re.search(r"Current Shiller PE Ratio is ([\d.]+)",
                       http_get("https://www.multpl.com/shiller-pe"))
        v["cape"] = (f"{float(mt.group(1)):.1f}", TODAY_S, True)
    except Exception:
        p = parse_prev(prev_md, r"Shiller CAPE约([\d.]+)倍（multpl，([^，）]*)")
        v["cape"] = (p[0], p[1], False) if p else ("41", "上期", False)
    p = parse_prev(prev_md, r"Fear & Greed (\d+)（CNN，([^，）]*)")  # CNN 反爬，直接沿用
    v["fng"] = (p[0], p[1], False) if p else ("46", "上期", False)
    p = parse_prev(prev_md, r"远期PE约([\d.]+)倍（FactSet，([^，）]*)")
    v["fwdpe"] = (p[0], p[1], False) if p else ("19.0", "上期", False)
    return v

# ---------- 规则化解读 ----------

def pct(x, nd=2):
    return f"{x:+.2f}%"

def us_commentary(m):
    spx, dji, ndx = m["SPX"], m["DJI"], m["NDX"]
    s = (f"美股最近交易日：标普500{pct(spx['day'])}报{spx['close']:,.2f}，"
         f"道指{pct(dji['day'])}，Nasdaq-100{pct(ndx['day'])}。")
    if ndx["day"] - dji["day"] > 1.0:
        s += "科技股显著强于蓝筹，资金偏成长。"
    elif dji["day"] - ndx["day"] > 1.0:
        s += "道指强、科技弱，资金从拥挤的AI交易向价值与防御轮动。"
    else:
        s += "三大指数方向基本一致。"
    if spx["dev250"] > 8:
        s += f"标普仍处年线上方约{spx['dev250']:.0f}%的高位区，估值容错空间小，维持“持有不追”。"
    elif spx["dev250"] < 0:
        s += "标普已跌破年线，趋势转弱，控制风险敞口为先。"
    else:
        s += "标普位于年线附近，方向待确认，维持既有仓位不追高。"
    return s

def cn_commentary(m):
    a, cx, cons = m["A500"], m["CHINEXT"], m["CONS50"]
    s = (f"A股最近交易日：中证A500{pct(a['day'])}，创业板指{pct(cx['day'])}，"
         f"中证消费50{pct(cons['day'])}。")
    if a["day"] < -1.5:
        s += "市场明显下挫，"
    elif a["day"] > 1.5:
        s += "市场明显反弹，"
    rel = cons["chg20"] - a["chg20"]
    if rel > 2:
        s += f"消费50近20日跑赢A500约{rel:.1f}pct，防御属性持续兑现；"
    if cx["chg20"] < -10:
        s += f"创业板指20日已跌{abs(cx['chg20']):.1f}%，科技成长仍在寻底，接飞刀为时过早，等连续缩量企稳信号。"
    elif cx["chg20"] < -5:
        s += "科技成长仍弱于大盘，加仓等企稳信号。"
    else:
        s += "成长与价值暂未明显分化。"
    return s

def nvda_commentary(nv):
    pos = (f"NVDA {nv['close']:.2f}美元（{pct(nv['day'])}），20日{pct(nv['chg20'])}，"
           f"MA50{('上方' if nv['dev50'] >= 0 else '下方')}约{abs(nv['dev50']):.0f}%，"
           f"MA200上方约{nv['dev200']:.0f}%。")
    if nv["dev50"] < 0:
        pos += ("股价跌破MA50，短期动能转弱，不抄底；已有仓位可持有，"
                "更好介入点在财报验证或接近MA200（约%.0f美元）且盈利预期未下修时。" % nv["ma200"])
    elif nv["dev50"] < 3:
        pos += "股价在MA50附近拉锯，不追，等财报或回踩企稳。"
    else:
        pos += "股价偏离MA50较多且拥挤度高，不追高，持有为主。"
    return pos

def abnb_commentary(ab):
    pos = (f"ABNB {ab['close']:.2f}美元（{pct(ab['day'])}），20日{pct(ab['chg20'])}，"
           f"MA50{('上方' if ab['dev50'] >= 0 else '下方')}约{abs(ab['dev50']):.0f}%，"
           f"MA200上方约{ab['dev200']:.0f}%。")
    if ab["dev50"] >= 0:
        pos += "重新站上MA50是积极信号，但需2–3个交易日确认守住再考虑小仓第一批；财报是下一验证点。"
    elif ab["dev200"] > 10:
        pos += "仍低于MA50、高于MA200，维持观察；重新站稳MA50或回踩150–155美元再考虑分批。"
    else:
        pos += "接近长期均线区域，若基本面未恶化可小仓分批，跌破前低需重新评估。"
    return pos

def portfolio_action(m):
    a = m["A500"]
    acts = ["核心仓位不减"]
    acts.append("暂停对拥挤科技方向的加仓" if m["NDX"]["dev250"] > 8 else "科技仓位持有为主")
    acts.append(f"A500继续分批（20日{pct(a['chg20'])}），节奏拉开间距" if a["chg20"] < -5
                else "A500按原计划小额分批")
    acts.append("新增资金优先消费50、恒指等估值与趋势相对友好的方向")
    acts.append("中证500/科创50/创业板指等连续缩量企稳信号再动")
    acts.append("个股：NVDA、ABNB均以财报与均线信号为准，不做重仓决定")
    return "；".join(acts) + "。"

# ---------- 文案组装 ----------

INDEX_ROWS = [
    ("SPX", "S&P 500", "美", "美股基准", "远期约19倍（中等）/ TTM偏高", "🟡"),
    ("DJI", "道指", "美", None, "中等", "🟢"),
    ("NDX", "Nasdaq-100", "美", None, "中等", "🔴"),
    ("HSI", "恒生指数", "港", "港股基准", "中等（PE约10.7倍）", "🟢"),
    ("HSTECH", "恒生科技", "港", None, "偏低（PE约22.6倍）", "🟢"),
    ("A500", "中证A500", "A", "A股基准", "中等偏低*", "🟢"),
    ("CSI500", "中证500", "A", None, "偏高（PE约31.9倍）", "🟢"),
    ("STAR50", "科创50", "A", None, "高", "🟢"),
    ("CHINEXT", "创业板指", "A", None, "中低", "🟢"),
    ("CONS50", "中证消费50", "A", None, "低（PE约17.7倍）", "🟢"),
]

def yearline(mt):
    d = mt["dev250"]
    ma = mt["ma250"]
    if d >= 8:
        return f"明显上方（约+{d:.0f}%）"
    if d >= 0:
        return f"上方（约+{d:.0f}%）"
    return f"年线下方约{abs(d):.0f}%（均线约{ma:,.0f}）"

def build_md(m, v, src, prev_md):
    base = {"美": "SPX", "港": "HSI", "A": "A500"}
    d_us, d_hk, d_a = m["SPX"]["date"], m["HSI"]["date"], m["A500"]["date"]
    lines = [f"# 全球投资市场简报 | {TITLE_DATE}", "",
             f"**数据截至：** 美股 {int(d_us[5:7])}月{int(d_us[8:10])}日收盘；港股 {int(d_hk[5:7])}月{int(d_hk[8:10])}日收盘；A股 {int(d_a[5:7])}月{int(d_a[8:10])}日收盘。",
             "**策略口径：** 面向未来约2个月和中长期配置；\"分批买入\"不是一次性加仓，默认分2–4批。", "",
             "| 指数 | 20交易日 | 相对强弱 | 估值 | 拥挤度 | 年线位置 |",
             "|---|---|---|---|---|---|"]
    for key, name, mkt, rel_label, val, crowd in INDEX_ROWS:
        mt = m[key]
        rel_name = {"美": "S&P", "港": "恒指", "A": "A500"}[mkt]
        rel = rel_label or f"较{rel_name} {mt['chg20']-m[base_of(mkt)]['chg20']:+.2f}pct"
        lines.append(f"| {name} | {pct(mt['chg20'])} | {rel} | {val} | {crowd} | {yearline(mt)} |")
    nv, ab = m["NVDA"], m["ABNB"]
    lines += ["", "## 个股持续观察", "",
              "| 个股 | 20交易日 | 相对S&P | 估值 | 拥挤度 | 趋势 |",
              "|---|---|---|---|---|---|",
              f"| Nvidia (NVDA) | {pct(nv['chg20'])} | {nv['chg20']-m['SPX']['chg20']:+.2f}pct | Fwd PE 约19倍 | 🔴 | MA50{('上方' if nv['dev50']>=0 else '下方')}约{abs(nv['dev50']):.0f}%；MA200上方约{nv['dev200']:.0f}% |",
              f"| Airbnb (ABNB) | {pct(ab['chg20'])} | {ab['chg20']-m['SPX']['chg20']:+.2f}pct | Fwd PE 约29倍（估算） | 🟢 | MA50{('上方' if ab['dev50']>=0 else '下方')}约{abs(ab['dev50']):.0f}%；MA200上方约{ab['dev200']:.0f}% |",
              "",
              f"**NVDA：** {nvda_commentary(nv)}",
              "",
              f"**ABNB：** {abnb_commentary(ab)}",
              "", "## 今日重点解读", "",
              f"**1. 美股：** {us_commentary(m)}",
              "",
              f"**2. A股与港股：** {cn_commentary(m)}恒指20日{pct(m['HSI']['chg20'])}、恒生科技{pct(m['HSTECH']['chg20'])}，估值分位中等偏低，风险收益比仍优于A股科技方向。",
              "",
              f"**3. 拥挤度与信用：** Shiller CAPE约{v['cape'][0]}倍（{v['cape'][1]}{'' if v['cape'][2] else '，未刷新'}）、高收益债OAS约{v['oas'][0]}%（{v['oas'][1]}{'' if v['oas'][2] else '，未刷新'}）、Fear & Greed {v['fng'][0]}（{v['fng'][1]}，未刷新）。利差走阔意味着信用端开始定价风险，组合层面保持防御权重。",
              "",
              f"**组合动作：** {portfolio_action(m)}",
              "", "---", "",
              f"**注：** 本版MA250均用K线实算（数据源：{('、'.join(sorted(set(src.values()))))}；本简报由云端定时任务自动生成）。估值数据日期：S&P 500远期PE约{v['fwdpe'][0]}倍（FactSet，{v['fwdpe'][1]}{'' if v['fwdpe'][2] else '，未刷新'}）、Shiller CAPE约{v['cape'][0]}倍（multpl，{v['cape'][1]}{'' if v['cape'][2] else '，未刷新'}）、Fear & Greed {v['fng'][0]}（CNN，{v['fng'][1]}，未刷新）、高收益债OAS约{v['oas'][0]}%（FRED/ICE BofA，{v['oas'][1]}{'' if v['oas'][2] else '，未刷新'}）；A股/港股指数PE及历史分位为既有口径，未逐一刷新。ABNB远期PE为估算值。以上为市场分析，不构成投资建议。"]
    return "\n".join(lines) + "\n"

def build_push(m, v):
    """Server酱 图文版 desp（移动排版，禁用 Markdown 表格）。"""
    nv, ab = m["NVDA"], m["ABNB"]
    d_us, d_hk, d_a = m["SPX"]["date"], m["HSI"]["date"], m["A500"]["date"]
    return "\n\n".join([
        f"**全球投资市场简报 | {TITLE_DATE}**",
        f"### 📂 [点这里 → 网站归档与历史简报]({SITE}/)",
        f"数据截至：美股 {int(d_us[5:7])}月{int(d_us[8:10])}日收盘；港股 {int(d_hk[5:7])}月{int(d_hk[8:10])}日收盘；A股 {int(d_a[5:7])}月{int(d_a[8:10])}日收盘",
        f"![指数总表]({SITE}/briefings/img/{TODAY_S}-table.png)",
        "**▍个股观察**\n\n" + nvda_commentary(nv) + "\n\n" + abnb_commentary(ab),
        "**▍今日重点**\n\n1. " + us_commentary(m) + "\n\n2. " + cn_commentary(m),
        "**▍组合动作**\n\n" + portfolio_action(m),
        "以上为市场分析，不构成投资建议。",
    ])

# ---------- 表格图片 ----------

def make_table_image(m, out_path):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager, pyplot as plt
    import glob
    for pat in ("/usr/share/fonts/**/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/**/NotoSansSC-Regular*",
                os.path.expanduser("~/Library/Application Support/kimi-desktop/daimon-share/daimon/runtime/python/fonts/NotoSansSC-*.ttf")):
        for f in glob.glob(pat, recursive=True):
            try:
                font_manager.fontManager.addfont(f)
            except Exception:
                pass
    plt.rcParams["font.family"] = ["Noto Sans CJK SC", "Noto Sans SC", "sans-serif"]
    cols = ["指数", "20交易日", "相对强弱", "年线位置", "拥挤度"]
    crowd_map = {"🟡": "中", "🟢": "低", "🔴": "高"}
    rows = []
    for key, name, mkt, rel_label, _, crowd in INDEX_ROWS:
        mt = m[key]
        rel_name = {"美": "S&P", "港": "恒指", "A": "A500"}[mkt]
        rel = rel_label or f"较{rel_name} {mt['chg20']-m[base_of(mkt)]['chg20']:+.2f}pct"
        yl = yearline(mt).replace("（均线约", "\n（均线约")
        rows.append([f"{mkt}·{name}", pct(mt["chg20"]), rel, yl, crowd_map[crowd]])
    crowd_color = {"低": "#dafbe1", "中": "#fff8c5", "高": "#ffebe9"}
    crowd_text = {"低": "#1a7f37", "中": "#9a6700", "高": "#cf222e"}
    fig, ax = plt.subplots(figsize=(11, 0.42 * len(rows) + 0.9), dpi=160)
    ax.axis("off")
    fig.text(0.03, 0.97, f"全球投资市场简报 · 指数总表（{TODAY_S}）",
             fontsize=15, fontweight="bold", va="top")
    d_us, d_hk, d_a = m["SPX"]["date"], m["HSI"]["date"], m["A500"]["date"]
    fig.text(0.03, 0.012,
             f"数据截至：美股 {d_us} / 港股 {d_hk} / A股 {d_a} 收盘；相对强弱为与各市场基准20日涨跌幅之差；年线为250日均线实算。",
             fontsize=8.5, color="#666", va="bottom")
    table = ax.table(cellText=rows, colLabels=cols, loc="upper center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    table.scale(1, 2.1)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#ddd")
        if r == 0:
            cell.set_facecolor("#f2f2f2")
            cell.set_text_props(fontweight="bold")
        elif c == 4:
            txt = cell.get_text().get_text()
            cell.set_facecolor(crowd_color.get(txt, "#fff"))
            cell.set_text_props(color=crowd_text.get(txt, "#333"))
        elif c == 1:
            txt = cell.get_text().get_text()
            cell.set_text_props(color="#1a7f37" if txt.startswith("+") else "#cf222e")
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)

def base_of(mkt):
    return {"美": "SPX", "港": "HSI", "A": "A500"}[mkt]

# ---------- git / 推送 ----------

def git(*args):
    subprocess.run(["git"] + list(args), check=True)

def server_chan(title, desp):
    keys = [k.strip() for k in os.environ.get("SCT_KEYS", "").split(",") if k.strip()]
    if not keys:
        print("SCT_KEYS 未配置，跳过微信推送")
        return
    for k in keys:
        for attempt in (0, 1):
            try:
                data = urllib.parse.urlencode({"title": title, "desp": desp}).encode()
                req = urllib.request.Request(f"https://sctapi.ftqq.com/{k}.send", data=data)
                with urllib.request.urlopen(req, timeout=20) as r:
                    resp = json.loads(r.read())
                print(f"push {k[:12]}...: {resp.get('data', {}).get('error') or resp}")
                break
            except Exception as e:
                print(f"push {k[:12]}... attempt{attempt} failed: {e}")
                time.sleep(30)

import urllib.parse

def latest_briefing_date():
    try:
        return json.load(open(f"{BRIEF_DIR}/index.json"))["briefings"][0]["date"]
    except Exception:
        return None

STATE_FILE = os.path.join(os.environ.get("BRIEF_DIR", "public/briefings"), ".state.json")

def read_state():
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {}

def write_state(m):
    json.dump({"us": m["SPX"]["date"], "hk": m["HSI"]["date"], "a": m["A500"]["date"],
               "briefing_date": TODAY_S},
              open(STATE_FILE, "w"), ensure_ascii=False, indent=2)

def phase_gen():
    prev = latest_briefing_date()
    prev_md = ""
    if prev:
        prev_md = open(f"{BRIEF_DIR}/{prev}.md", encoding="utf-8").read()
    m, src = collect()
    sig = {"us": m["SPX"]["date"], "hk": m["HSI"]["date"], "a": m["A500"]["date"]}
    st = read_state()
    no_new_data = (sig["us"] == st.get("us") and sig["hk"] == st.get("hk")
                   and sig["a"] == st.get("a"))
    if (latest_briefing_date() == TODAY_S or no_new_data) and not os.environ.get("FORCE"):
        print(f"无需更新（简报日期={latest_briefing_date()}，数据口径={sig}），静默跳过")
        json.dump({"status": "skipped"}, open("/tmp/gen_result.json", "w"))
        return "skip"
    print(json.dumps({k: {"date": v["date"], "close": round(v["close"], 2),
                          "chg20": round(v["chg20"], 2)} for k, v in m.items()},
                     ensure_ascii=False, indent=1))
    v = refresh_valuations(prev_md)
    md = build_md(m, v, src, prev_md)
    open(f"{BRIEF_DIR}/{TODAY_S}.md", "w", encoding="utf-8").write(md)
    os.makedirs(f"{BRIEF_DIR}/img", exist_ok=True)
    make_table_image(m, f"{BRIEF_DIR}/img/{TODAY_S}-table.png")
    idx = json.load(open(f"{BRIEF_DIR}/index.json"))
    idx["briefings"].insert(0, {"date": TODAY_S, "title": f"全球投资市场简报 | {TITLE_DATE}"})
    json.dump(idx, open(f"{BRIEF_DIR}/index.json", "w"), ensure_ascii=False, indent=2)
    # 推送内容存文件供 notify 阶段使用
    json.dump({"title": f"简报 {TODAY.month}月{TODAY.day}日｜已发布｜标普 {m['SPX']['day']:+.1f}% 恒指 {m['HSI']['day']:+.1f}% A500 {m['A500']['day']:+.1f}%",
               "desp": build_push(m, v)},
              open("/tmp/push_payload.json", "w"), ensure_ascii=False)
    write_state(m)
    json.dump({"status": "published"}, open("/tmp/gen_result.json", "w"))
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN：不提交不推送")
        return "dry"
    git("add", BRIEF_DIR)
    git("-c", "user.name=github-actions", "-c", "user.email=actions@github.com",
        "commit", "-m", f"briefing {TODAY_S}")
    git("push", "origin", "main")
    return "ok"

def phase_notify():
    try:
        gen_status = json.load(open("/tmp/gen_result.json")).get("status")
    except Exception:
        gen_status = "unknown"
    if gen_status == "skipped":
        # 静默休息日：只做健康检查，网站异常才提醒
        try:
            http_get(SITE + "/")
            http_get(f"{SITE}/briefings/index.json")
            print("休息日静默跳过，网站健康检查通过")
        except Exception as e:
            server_chan(f"简报 {TODAY.month}月{TODAY.day}日｜异常",
                        f"网站健康检查失败：{e!r}\n\n{SITE}")
        return
    ok = False
    for i in range(3):
        try:
            body = http_get(f"{SITE}/briefings/index.json")
            img_ok = http_get(f"{SITE}/briefings/img/{TODAY_S}-table.png") is not None
            if TODAY_S in body:
                ok = True
                break
        except Exception as e:
            print(f"verify attempt{i}: {e}")
        time.sleep(30)
    try:
        payload = json.load(open("/tmp/push_payload.json"))
    except Exception:
        payload = None
    if ok and payload:
        server_chan(payload["title"], payload["desp"])
    elif ok:
        server_chan(f"简报 {TODAY.month}月{TODAY.day}日｜已是最新，跳过",
                    f"### 📂 [网站归档]({SITE}/)\n\n今日无需更新（最新交易日已覆盖），网站运行正常。\n\n以上为市场分析，不构成投资建议。")
    else:
        server_chan(f"简报 {TODAY.month}月{TODAY.day}日｜异常",
                    f"云端任务异常：网站验证未通过（{SITE}）。请检查 GitHub Actions 运行日志。\n\n以上为市场分析，不构成投资建议。")
    print("notify done, site_ok =", ok)

if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "gen"
    try:
        if phase == "gen":
            phase_gen()
        elif phase == "notify":
            phase_notify()
    except Exception as e:
        print("FATAL:", repr(e))
        try:
            server_chan(f"简报 {TODAY.month}月{TODAY.day}日｜异常",
                        f"云端任务执行失败：{e!r}\n\n请检查 GitHub Actions 日志。")
        finally:
            sys.exit(1)
