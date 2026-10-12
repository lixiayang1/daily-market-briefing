import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface BriefingMeta {
  date: string;
  title: string;
}

interface IndexData {
  briefings: BriefingMeta[];
}

export default function App() {
  const [indexData, setIndexData] = useState<IndexData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}briefings/index.json`)
      .then((r) => {
        if (!r.ok) throw new Error("index.json 加载失败");
        return r.json();
      })
      .then((data: IndexData) => {
        const sorted = [...data.briefings].sort((a, b) => b.date.localeCompare(a.date));
        setIndexData({ briefings: sorted });
        if (sorted.length > 0) setSelected(sorted[0].date);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    fetch(`${import.meta.env.BASE_URL}briefings/${selected}.md`)
      .then((r) => {
        if (!r.ok) throw new Error("简报加载失败");
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

  const currentTitle = useMemo(
    () => indexData?.briefings.find((b) => b.date === selected)?.title ?? "",
    [indexData, selected]
  );

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
        <p className="text-muted-foreground">加载失败：{error}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border sticky top-0 bg-background/95 backdrop-blur z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">每日投资简报</h1>
            <p className="text-sm text-muted-foreground">全球投资市场 · 每个交易日更新</p>
          </div>
          {selected && (
            <span className="text-sm font-medium px-3 py-1 rounded-full bg-primary/10 text-primary">
              {selected}
            </span>
          )}
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-6 flex gap-6">
        <aside className="w-48 shrink-0 hidden md:block">
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            历史简报
          </h2>
          <nav className="space-y-1">
            {indexData?.briefings.map((b) => (
              <button
                key={b.date}
                onClick={() => setSelected(b.date)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-md text-sm transition-colors",
                  b.date === selected
                    ? "bg-primary text-primary-foreground font-medium"
                    : "hover:bg-muted text-muted-foreground hover:text-foreground"
                )}
              >
                {b.date}
              </button>
            ))}
          </nav>
        </aside>

        <main className="flex-1 min-w-0">
          <div className="md:hidden mb-4">
            <select
              value={selected ?? ""}
              onChange={(e) => setSelected(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm"
            >
              {indexData?.briefings.map((b) => (
                <option key={b.date} value={b.date}>
                  {b.date} — {b.title}
                </option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="space-y-4 animate-pulse">
              <div className="h-8 bg-muted rounded w-2/3" />
              <div className="h-4 bg-muted rounded w-1/3" />
              <div className="h-64 bg-muted rounded" />
            </div>
          ) : (
            <article className="briefing-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </article>
          )}
        </main>
      </div>

      <footer className="border-t border-border mt-12">
        <div className="max-w-6xl mx-auto px-4 py-4 text-xs text-muted-foreground">
          {currentTitle} · 数据与观点仅供研究参考，不构成投资建议
        </div>
      </footer>
    </div>
  );
}
