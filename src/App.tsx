import { useEffect, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface BriefingMeta {
  date: string;
  title: string;
}

interface IndexData {
  briefings: BriefingMeta[];
}

const NUM_RE = /([+-]\d+(?:\.\d+)?(?:%|pct))/g;

/** 涨跌着色：中文习惯 红涨绿跌 */
function colorize(text: string): ReactNode[] {
  const parts = text.split(NUM_RE);
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      const up = part.startsWith("+");
      return (
        <span key={i} className={up ? "text-up font-semibold" : "text-down font-semibold"}>
          {part}
        </span>
      );
    }
    return part;
  });
}

function renderChildren(children: ReactNode): ReactNode {
  if (typeof children === "string") return colorize(children);
  if (Array.isArray(children)) return children.map((c, i) => <span key={i}>{renderChildren(c)}</span>);
  if (children && typeof children === "object" && "props" in (children as any)) {
    const el = children as React.ReactElement<{ children?: ReactNode }>;
    return { ...el, props: { ...el.props, children: renderChildren(el.props.children) } };
  }
  return children;
}

const mdComponents = {
  h1: ({ children }: any) => (
    <h1 className="text-[22px] md:text-2xl font-bold tracking-tight text-ink leading-snug">
      {renderChildren(children)}
    </h1>
  ),
  h2: ({ children }: any) => (
    <h2 className="flex items-center gap-2 text-[17px] font-bold mt-10 mb-4 text-ink">
      <span className="inline-block w-1 h-4 rounded-full bg-accent" />
      {renderChildren(children)}
    </h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="text-[15px] font-semibold mt-6 mb-2 text-ink">{renderChildren(children)}</h3>
  ),
  p: ({ children }: any) => (
    <p className="my-3 text-[14.5px] leading-7 text-ink/90">{renderChildren(children)}</p>
  ),
  strong: ({ children }: any) => (
    <strong className="font-semibold text-ink">{renderChildren(children)}</strong>
  ),
  hr: () => <hr className="my-6 border-border" />,
  ul: ({ children }: any) => <ul className="my-3 pl-5 space-y-1.5 list-disc marker:text-muted">{children}</ul>,
  ol: ({ children }: any) => <ol className="my-3 pl-5 space-y-1.5 list-decimal marker:text-muted">{children}</ol>,
  li: ({ children }: any) => <li className="text-[14.5px] leading-7 text-ink/90">{renderChildren(children)}</li>,
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-[3px] border-accent/50 bg-accent/[0.04] rounded-r-lg px-4 py-1 my-4 text-ink/80">
      {children}
    </blockquote>
  ),
  a: ({ href, children }: any) => (
    <a
      href={defaultUrlTransform(href)}
      target="_blank"
      rel="noreferrer"
      className="text-accent hover:underline"
    >
      {children}
    </a>
  ),
  code: ({ children }: any) => (
    <code className="px-1.5 py-0.5 rounded-md bg-ink/[0.05] text-[13px] font-mono text-ink/85">
      {children}
    </code>
  ),
  table: ({ children }: any) => (
    <div className="md-table my-5 overflow-x-auto rounded-xl border border-border bg-white shadow-sm">
      <table className="w-full text-[13.5px] border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }: any) => (
    <thead className="bg-navy/[0.04] text-ink/70">{children}</thead>
  ),
  th: ({ children }: any) => (
    <th className="text-left font-semibold px-3.5 py-2.5 border-b border-border whitespace-nowrap text-[13px]">
      {renderChildren(children)}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="px-3.5 py-2.5 border-b border-border/60 align-top whitespace-nowrap">
      {renderChildren(children)}
    </td>
  ),
  tr: ({ children }: any) => <tr>{children}</tr>,
};

export default function App() {
  const [indexData, setIndexData] = useState<IndexData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}briefings/index.json`)
      .then((r) => {
        if (!r.ok) throw new Error("简报索引加载失败");
        return r.json();
      })
      .then((data: IndexData) => {
        const sorted = [...data.briefings].sort((a, b) => b.date.localeCompare(a.date));
        setIndexData({ briefings: sorted });
        if (sorted.length > 0) setSelected(sorted[0].date);
        else setError("还没有任何简报");
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    fetch(`${import.meta.env.BASE_URL}briefings/${selected}.md`)
      .then((r) => {
        if (!r.ok) throw new Error("简报内容加载失败");
        return r.text();
      })
      .then((text) => {
        setContent(text);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [selected]);

  const current = useMemo(
    () => indexData?.briefings.find((b) => b.date === selected),
    [indexData, selected]
  );

  if (error && !indexData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-page">
        <div className="text-center">
          <p className="text-3xl mb-2">📭</p>
          <p className="text-muted">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page">
      {/* Header */}
      <header className="bg-navy text-white sticky top-0 z-20 shadow-md">
        <div className="max-w-6xl mx-auto px-4 md:px-6 h-14 flex items-center gap-3">
          <div className="flex items-center gap-2.5 shrink-0">
            <span className="grid place-items-center w-8 h-8 rounded-lg bg-accent/90 text-white text-sm font-bold">
              简
            </span>
            <div className="leading-tight">
              <div className="font-bold text-[15px] tracking-wide">每日投资简报</div>
              <div className="text-[10.5px] text-white/50 hidden sm:block">
                Global Market Briefing · 交易日更新
              </div>
            </div>
          </div>

          <div className="flex-1" />

          <select
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value)}
            className="bg-white/10 hover:bg-white/15 text-white text-[13px] rounded-lg pl-3 pr-8 py-1.5 border border-white/20 outline-none cursor-pointer appearance-none bg-no-repeat transition-colors"
            style={{
              backgroundImage:
                "url(\"data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e\")",
              backgroundSize: "14px",
              backgroundPosition: "right 10px center",
            }}
            aria-label="选择日期"
          >
            {indexData?.briefings.map((b) => (
              <option key={b.date} value={b.date} className="text-ink">
                {b.date}
              </option>
            ))}
          </select>

          <a
            href="https://github.com/lixiayang1/daily-market-briefing"
            target="_blank"
            rel="noreferrer"
            className="hidden md:inline-flex text-white/60 hover:text-white text-[12px] transition-colors"
          >
            GitHub ↗
          </a>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 flex gap-6 items-start">
        {/* Sidebar archive */}
        <aside className="w-52 shrink-0 hidden lg:block sticky top-[72px]">
          <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-border bg-navy/[0.03]">
              <h2 className="text-[12px] font-bold text-ink/70 uppercase tracking-wider">
                往期简报
              </h2>
            </div>
            <nav className="p-1.5 max-h-[60vh] overflow-y-auto">
              {indexData?.briefings.map((b, i) => (
                <button
                  key={b.date}
                  onClick={() => setSelected(b.date)}
                  className={cn(
                    "w-full text-left px-3 py-2 rounded-lg text-[13px] transition-colors flex items-center gap-2",
                    b.date === selected
                      ? "bg-accent text-white font-semibold shadow-sm"
                      : "hover:bg-ink/[0.04] text-ink/70 hover:text-ink"
                  )}
                >
                  <span>{b.date}</span>
                  {i === 0 && (
                    <span
                      className={cn(
                        "ml-auto text-[10px] px-1.5 py-0.5 rounded-full",
                        b.date === selected
                          ? "bg-white/20 text-white"
                          : "bg-up/10 text-up"
                      )}
                    >
                      最新
                    </span>
                  )}
                </button>
              ))}
            </nav>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0">
          {/* Title bar */}
          <div className="bg-gradient-to-r from-navy to-[#1d3461] text-white rounded-xl px-5 py-4 mb-5 shadow-sm">
            <div className="text-[11px] text-white/60 mb-1 tracking-wider">全球投资市场简报</div>
            <h1 className="text-lg md:text-xl font-bold tracking-tight">
              {current?.title ?? "加载中…"}
            </h1>
          </div>

          <div className="bg-white rounded-xl border border-border shadow-sm px-5 py-6 md:px-8 md:py-8">
            {loading ? (
              <div className="space-y-4 animate-pulse pt-1">
                <div className="h-7 bg-ink/[0.06] rounded w-2/3" />
                <div className="h-4 bg-ink/[0.06] rounded w-1/3" />
                <div className="h-52 bg-ink/[0.05] rounded-xl mt-6" />
                <div className="h-4 bg-ink/[0.06] rounded w-5/6" />
                <div className="h-4 bg-ink/[0.06] rounded w-4/6" />
              </div>
            ) : error ? (
              <p className="text-muted">{error}</p>
            ) : (
              <article>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                  {content}
                </ReactMarkdown>
              </article>
            )}
          </div>
        </main>
      </div>

      <footer className="mt-10 border-t border-border bg-white">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-5 text-[12px] text-muted flex flex-col sm:flex-row gap-1 sm:items-center sm:justify-between">
          <span>每日投资简报 · 数据与观点仅供研究参考，不构成投资建议</span>
          <span>
            由 Kimi Work 自动生成 ·{" "}
            <a
              className="hover:text-accent"
              href="https://github.com/lixiayang1/daily-market-briefing"
              target="_blank"
              rel="noreferrer"
            >
              lixiayang1/daily-market-briefing
            </a>
          </span>
        </div>
      </footer>
    </div>
  );
}
