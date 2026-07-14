import React, { useState } from "react";
import { api } from "./api.js";

const TABS = [
  { key: "clues", label: "线索" },
  { key: "branches", label: "破壁" },
  { key: "idioms", label: "找词" },
  { key: "quotes", label: "引经" },
];

export default function MusePanel({ projectId, chapter }) {
  const [tab, setTab] = useState("clues");
  return (
    <aside className="muse">
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? "active" : ""}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "clues" && <CluesPane projectId={projectId} />}
      {tab === "branches" && <BranchesPane projectId={projectId} chapter={chapter} />}
      {tab === "idioms" && <IdiomsPane />}
      {tab === "quotes" && <QuotesPane />}
    </aside>
  );
}

function usePane(fetcher) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setItems(await fetcher(query.trim()));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  return { query, setQuery, items, loading, error, run };
}

function AskForm({ pane, placeholder, action }) {
  return (
    <form
      className="ask"
      onSubmit={(e) => {
        e.preventDefault();
        pane.run();
      }}
    >
      <input
        value={pane.query}
        placeholder={placeholder}
        onChange={(e) => pane.setQuery(e.target.value)}
      />
      <button className="btn ghost" type="submit" disabled={pane.loading}>
        {action}
      </button>
    </form>
  );
}

const SOURCE_LABEL = {
  character: "角色",
  world: "世界观",
  foreshadowing: "伏笔",
};

function CluesPane({ projectId }) {
  const pane = usePane(async (q) => (await api.retrieve(projectId, q)).chunks);
  return (
    <div className="pane">
      <AskForm pane={pane} placeholder="描述当前场景，找相关设定" action="检索" />
      {pane.error && <p className="error">{pane.error}</p>}
      {pane.loading && <p className="loading">在设定库里翻找…</p>}
      {pane.items && pane.items.length === 0 && (
        <p className="empty">没有找到相关设定。先在设定库里存些角色和世界观。</p>
      )}
      {pane.items?.map((c) => (
        <div className="slip" key={c.id} style={{ "--slip-heat": Math.max(c.score, 0.25) }}>
          <div className="slip-head">
            <span className="slip-tag">{SOURCE_LABEL[c.source_type] || c.source_type}</span>
            <span className="slip-score">{c.score.toFixed(3)}</span>
          </div>
          <p className="slip-body">{c.content}</p>
        </div>
      ))}
      {pane.items === null && !pane.loading && (
        <p className="empty">
          这里是 RAG 的观察窗：
          <br />
          输入一句场景描述，看检索层会把哪些设定喂给模型。
        </p>
      )}
    </div>
  );
}

function BranchesPane({ projectId, chapter }) {
  const pane = usePane(async (q) => {
    if (!chapter) throw new Error("先选择一个章节");
    return (await api.breakthrough(projectId, chapter.id, q)).branches;
  });
  return (
    <div className="pane">
      <AskForm pane={pane} placeholder="一句话描述当前剧情卡点" action="破壁" />
      {pane.error && <p className="error">{pane.error}</p>}
      {pane.loading && <p className="loading">在岔路口点灯…（约需十几秒）</p>}
      {pane.items?.map((b, i) => (
        <div className="branch" key={i}>
          <span className="branch-dir">{b.direction}</span>
          <h4>{b.title}</h4>
          <p>{b.outline}</p>
        </div>
      ))}
      {pane.items === null && !pane.loading && (
        <p className="empty">
          卡文的时候来这里：
          <br />
          描述剧情现状，一次拿到三条走向不同的岔路。
        </p>
      )}
    </div>
  );
}

function IdiomsPane() {
  const pane = usePane(async (q) => (await api.suggestIdioms(q)).suggestions);
  return (
    <div className="pane">
      <AskForm pane={pane} placeholder="描述想形容的画面" action="找词" />
      {pane.error && <p className="error">{pane.error}</p>}
      {pane.loading && <p className="loading">在成语库里挑选…</p>}
      {pane.items && pane.items.length === 0 && (
        <p className="empty">成语库还是空的。先运行 seed_idioms.py 灌入数据。</p>
      )}
      {pane.items?.map((s) => (
        <div className="slip" key={s.text} style={{ "--slip-heat": Math.max(s.score, 0.25) }}>
          <div className="slip-head">
            <span className="slip-tag">成语</span>
            <span className="slip-score">{s.score.toFixed(3)}</span>
          </div>
          <p className="slip-body">
            <strong>{s.text}</strong> — {s.meaning}
            {s.reason && (
              <>
                <br />
                {s.reason}
              </>
            )}
          </p>
        </div>
      ))}
      {pane.items === null && !pane.loading && (
        <p className="empty">
          词穷的时候来这里：
          <br />
          描述画面，从真实成语库里召回精准的词。
        </p>
      )}
    </div>
  );
}

function QuotesPane() {
  const pane = usePane(async (q) => (await api.literaryQuotes(q)).quotes);
  return (
    <div className="pane">
      <AskForm pane={pane} placeholder="当前情节的主题，如：爱情与想象" action="引经" />
      {pane.error && <p className="error">{pane.error}</p>}
      {pane.loading && <p className="loading">在文学库里检索…</p>}
      {pane.items && pane.items.length === 0 && (
        <p className="empty">文学库还是空的。先运行 seed_literary.py 灌入数据。</p>
      )}
      {pane.items?.map((qt, i) => (
        <div className="slip" key={i} style={{ "--slip-heat": Math.max(qt.score, 0.25) }}>
          <div className="slip-head">
            <span className="slip-tag">{qt.knowledge_type}</span>
            <span className="slip-score">{qt.score.toFixed(3)}</span>
          </div>
          <p className="slip-body">
            <strong>
              《{qt.work_title}》· {qt.author}
              {qt.era ? `（${qt.era}）` : ""}
            </strong>
            <br />
            {qt.content}
          </p>
        </div>
      ))}
      {pane.items === null && !pane.loading && (
        <p className="empty">
          让角色引经据典：
          <br />
          输入主题，检索公有领域文学知识，杜绝张冠李戴。
        </p>
      )}
    </div>
  );
}
