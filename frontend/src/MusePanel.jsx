import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// Three sections, each with focused windows:
//   架构 — the world's skeleton: retrieval clues, material ingest, settings, threads
//   行文 — the sentence level: citations, idioms
//   创作 — generation: breakthrough branches, vetted imitation
const SECTIONS = [
  {
    key: "arch",
    label: "架构",
    tabs: [
      { key: "clues", label: "线索" },
      { key: "ingest", label: "素材" },
      { key: "settings", label: "设定" },
      { key: "threads", label: "伏笔" },
    ],
  },
  {
    key: "prose",
    label: "行文",
    tabs: [
      { key: "quotes", label: "引经" },
      { key: "idioms", label: "找词" },
    ],
  },
  {
    key: "create",
    label: "创作",
    tabs: [
      { key: "branches", label: "破壁" },
      { key: "imitate", label: "仿写" },
    ],
  },
];

export default function MusePanel({ projectId, chapter, onAppend }) {
  const [sectionKey, setSectionKey] = useState("arch");
  const section = SECTIONS.find((s) => s.key === sectionKey);
  const [tabKey, setTabKey] = useState(section.tabs[0].key);

  const switchSection = (key) => {
    setSectionKey(key);
    setTabKey(SECTIONS.find((s) => s.key === key).tabs[0].key);
  };

  return (
    <aside className="muse">
      <div className="sections" role="tablist" aria-label="版块">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            role="tab"
            aria-selected={sectionKey === s.key}
            className={sectionKey === s.key ? "active" : ""}
            onClick={() => switchSection(s.key)}
          >
            {s.label}
          </button>
        ))}
      </div>
      <div className="tabs" role="tablist" aria-label="窗口">
        {section.tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tabKey === t.key}
            className={tabKey === t.key ? "active" : ""}
            onClick={() => setTabKey(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabKey === "clues" && <CluesPane projectId={projectId} chapter={chapter} />}
      {tabKey === "ingest" && <IngestPane projectId={projectId} />}
      {tabKey === "settings" && <SettingsPane projectId={projectId} />}
      {tabKey === "threads" && <ThreadsPane projectId={projectId} chapter={chapter} />}
      {tabKey === "quotes" && <QuotesPane />}
      {tabKey === "idioms" && <IdiomsPane />}
      {tabKey === "branches" && <BranchesPane projectId={projectId} chapter={chapter} />}
      {tabKey === "imitate" && (
        <ImitatePane projectId={projectId} chapter={chapter} onAppend={onAppend} />
      )}
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
  style: "文风",
};

/* ---------- 架构 ---------- */

function CluesPane({ projectId, chapter }) {
  const [fragment, setFragment] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = async () => {
    if (fragment.trim().length < 10) {
      setError("给我一段正文（至少十个字），而不是一句概括。");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await api.composeHints(projectId, fragment.trim()));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const useChapterTail = () => {
    if (chapter?.content) setFragment(chapter.content.slice(-300));
  };

  return (
    <div className="pane">
      <p className="pane-hint">
        贴一段正文，参谋会告诉你：哪些<strong>设定能在此处驱动情节</strong>、
        素材库里有什么<strong>母题方向</strong>可以流向，以及一个整合的走向建议。
      </p>
      <textarea
        className="ingest-text"
        rows={4}
        value={fragment}
        placeholder="粘贴当前写到的正文片段…"
        onChange={(e) => setFragment(e.target.value)}
      />
      <div className="ingest-actions">
        <button className="btn ghost" onClick={useChapterTail} disabled={!chapter}>
          取本章结尾
        </button>
        <button className="btn primary" onClick={run} disabled={loading}>
          {loading ? "参谋思考中…" : "问参谋"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}

      {result && (
        <>
          {result.organization && (
            <div className="counsel-org">{result.organization}</div>
          )}
          {result.drivers.length > 0 && <h3 className="pane-title">设定 · 驱动</h3>}
          {result.drivers.map((d, i) => (
            <div className="slip" key={`d${i}`} style={{ "--slip-heat": Math.max(d.score, 0.25) }}>
              <div className="slip-head">
                <span className="slip-tag">{SOURCE_LABEL[d.source_type] || d.source_type}</span>
                <span className="slip-score">{d.score.toFixed(3)}</span>
              </div>
              <p className="slip-body">
                <strong>{d.suggestion}</strong>
                <br />
                <span className="cite">依据：{d.content.slice(0, 60)}</span>
              </p>
            </div>
          ))}
          {result.directions.length > 0 && <h3 className="pane-title">素材 · 方向</h3>}
          {result.directions.map((d, i) => (
            <div className="slip" key={`m${i}`} style={{ "--slip-heat": Math.max(d.score, 0.25) }}>
              <div className="slip-head">
                <span className="slip-tag">《{d.work_title}》</span>
                <span className="slip-score">{d.score.toFixed(3)}</span>
              </div>
              <p className="slip-body">
                <strong>{d.suggestion}</strong>
                <br />
                <span className="cite">{d.author} · {d.knowledge_type}：{d.content.slice(0, 50)}</span>
              </p>
            </div>
          ))}
          <details className="debug-view">
            <summary>调试视图：原始检索命中</summary>
            {result.raw_settings.map((c) => (
              <div className="slip" key={c.id} style={{ "--slip-heat": 0.3 }}>
                <div className="slip-head">
                  <span className="slip-tag">{SOURCE_LABEL[c.source_type] || c.source_type}</span>
                  <span className="slip-score">{c.score.toFixed(3)}</span>
                </div>
                <p className="slip-body">{c.content}</p>
              </div>
            ))}
            {result.raw_literary.map((q, i) => (
              <div className="slip" key={`rl${i}`} style={{ "--slip-heat": 0.3 }}>
                <div className="slip-head">
                  <span className="slip-tag">《{q.work_title}》</span>
                  <span className="slip-score">{q.score.toFixed(3)}</span>
                </div>
                <p className="slip-body">{q.content}</p>
              </div>
            ))}
          </details>
        </>
      )}
      {!result && !loading && (
        <p className="empty">
          写不下去的段落，正是参谋的用武之地。
          <br />
          检索出的每条建议都有出处，绝不凭空编造。
        </p>
      )}
    </div>
  );
}

function chunkText(text, target = 400, min = 150) {
  const paras = text.split(/\n+/).map((p) => p.trim()).filter(Boolean);
  const chunks = [];
  let buf = [];
  let size = 0;
  for (const p of paras) {
    buf.push(p);
    size += p.length;
    if (size >= target) {
      chunks.push(buf.join("\n"));
      buf = [];
      size = 0;
    }
  }
  if (buf.length && size >= min) chunks.push(buf.join("\n"));
  return chunks;
}

function IngestPane({ projectId }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [samples, setSamples] = useState(null);
  const [error, setError] = useState(null);

  const reload = async () => setSamples(await api.listStyleSamples(projectId));
  useEffect(() => {
    reload().catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const readFile = (file) => {
    const reader = new FileReader();
    reader.onload = () => setText(String(reader.result || ""));
    reader.readAsText(file);
  };

  const submit = async () => {
    const chunks = chunkText(text);
    if (chunks.length === 0) {
      setError("文字太短，至少一段 150 字以上。");
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      for (const c of chunks) await api.addStyleSample(projectId, c);
      setReport(`已切成 ${chunks.length} 段样本入库。`);
      setText("");
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pane">
      <p className="pane-hint">
        粘贴文字或选择 .txt 文件，自动切块进入<strong>私有文风库</strong>——
        仿写与续写会从这里召回语感。整本 epub 用后端脚本导入。
      </p>
      <textarea
        className="ingest-text"
        rows={6}
        value={text}
        placeholder="粘贴一段你想让 AI 学习语感的文字…"
        onChange={(e) => setText(e.target.value)}
      />
      <div className="ingest-actions">
        <label className="btn ghost file-btn">
          选 .txt 文件
          <input
            type="file"
            accept=".txt"
            hidden
            onChange={(e) => e.target.files[0] && readFile(e.target.files[0])}
          />
        </label>
        <button className="btn primary" onClick={submit} disabled={busy || !text.trim()}>
          {busy ? "入库中…" : "切块入库"}
        </button>
      </div>
      {report && <p className="ok">{report}</p>}
      {error && <p className="error">{error}</p>}
      {samples && (
        <p className="pane-hint">
          文风库现有 <strong>{samples.length}</strong> 段样本。
        </p>
      )}
    </div>
  );
}

function SettingsPane({ projectId }) {
  const [characters, setCharacters] = useState([]);
  const [world, setWorld] = useState([]);
  const [error, setError] = useState(null);
  const [charForm, setCharForm] = useState({ name: "", persona: "", summary: "" });
  const [worldForm, setWorldForm] = useState({ category: "规则", title: "", content: "" });

  const reload = async () => {
    setCharacters(await api.listCharacters(projectId));
    setWorld(await api.listWorld(projectId));
  };
  useEffect(() => {
    reload().catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const addCharacter = async (e) => {
    e.preventDefault();
    if (!charForm.name.trim()) return;
    const persona = {};
    for (const line of charForm.persona.split("\n")) {
      const m = line.match(/^(.+?)[:：](.+)$/);
      if (m) persona[m[1].trim()] = m[2].trim();
    }
    try {
      await api.createCharacter(projectId, {
        name: charForm.name.trim(),
        persona,
        summary: charForm.summary.trim() || null,
      });
      setCharForm({ name: "", persona: "", summary: "" });
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };

  const addWorld = async (e) => {
    e.preventDefault();
    if (!worldForm.title.trim() || !worldForm.content.trim()) return;
    try {
      await api.createWorld(projectId, {
        category: worldForm.category,
        title: worldForm.title.trim(),
        content: worldForm.content.trim(),
      });
      setWorldForm({ category: worldForm.category, title: "", content: "" });
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="pane">
      {error && <p className="error">{error}</p>}

      <h3 className="pane-title">角色</h3>
      <form className="thread-form" onSubmit={addCharacter}>
        <input
          value={charForm.name}
          placeholder="角色名"
          onChange={(e) => setCharForm({ ...charForm, name: e.target.value })}
        />
        <textarea
          rows={2}
          value={charForm.persona}
          placeholder={"每行一条特质，如：\n性格：外冷内热\n能力：言灵S级"}
          onChange={(e) => setCharForm({ ...charForm, persona: e.target.value })}
        />
        <input
          value={charForm.summary}
          placeholder="一句话简介（可选）"
          onChange={(e) => setCharForm({ ...charForm, summary: e.target.value })}
        />
        <button className="btn primary" type="submit">
          存入角色
        </button>
      </form>
      {characters.map((c) => (
        <div className="slip" key={c.id} style={{ "--slip-heat": 0.6 }}>
          <div className="slip-head">
            <span className="slip-tag">角色</span>
            <span className="thread-actions">
              <button onClick={() => api.deleteCharacter(projectId, c.id).then(reload)}>
                删除
              </button>
            </span>
          </div>
          <p className="slip-body">
            <strong>{c.name}</strong>
            {c.summary ? ` — ${c.summary}` : ""}
          </p>
        </div>
      ))}

      <h3 className="pane-title">世界观</h3>
      <form className="thread-form" onSubmit={addWorld}>
        <select
          value={worldForm.category}
          onChange={(e) => setWorldForm({ ...worldForm, category: e.target.value })}
        >
          {["规则", "势力", "地点", "力量体系", "其他"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <input
          value={worldForm.title}
          placeholder="条目标题，如：夜幕协定"
          onChange={(e) => setWorldForm({ ...worldForm, title: e.target.value })}
        />
        <textarea
          rows={2}
          value={worldForm.content}
          placeholder="设定内容"
          onChange={(e) => setWorldForm({ ...worldForm, content: e.target.value })}
        />
        <button className="btn primary" type="submit">
          存入世界观
        </button>
      </form>
      {world.map((w) => (
        <div className="slip" key={w.id} style={{ "--slip-heat": 0.6 }}>
          <div className="slip-head">
            <span className="slip-tag">{w.category}</span>
            <span className="thread-actions">
              <button onClick={() => api.deleteWorld(projectId, w.id).then(reload)}>
                删除
              </button>
            </span>
          </div>
          <p className="slip-body">
            <strong>{w.title}</strong> — {w.content}
          </p>
        </div>
      ))}
    </div>
  );
}

function ThreadsPane({ projectId, chapter }) {
  const [threads, setThreads] = useState(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState(null);

  const reload = async () => {
    try {
      setThreads(await api.listForeshadowing(projectId));
    } catch (err) {
      setError(err.message);
    }
  };
  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const add = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setError(null);
    try {
      await api.createForeshadowing(projectId, {
        title: title.trim(),
        content: content.trim() || null,
        setup_chapter_id: chapter?.id ?? null,
      });
      setTitle("");
      setContent("");
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };

  const toggle = async (t) => {
    const patch =
      t.status === "open"
        ? { status: "closed", payoff_chapter_id: chapter?.id ?? null }
        : { status: "open", payoff_chapter_id: null };
    await api.updateForeshadowing(projectId, t.id, patch);
    await reload();
  };

  return (
    <div className="pane">
      <form className="thread-form" onSubmit={add}>
        <input
          value={title}
          placeholder="伏笔标题，如：老周留下的铭文"
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          value={content}
          rows={2}
          placeholder="细节（可选）：埋了什么、暗示什么"
          onChange={(e) => setContent(e.target.value)}
        />
        <button className="btn primary" type="submit">
          埋下伏笔
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {threads && threads.length === 0 && (
        <p className="empty">
          还没有伏笔。
          <br />
          埋下的伏笔会进入检索库，续写时自动被想起。
        </p>
      )}
      {threads?.map((t) => (
        <div
          className="slip"
          key={t.id}
          style={{ "--slip-heat": t.status === "open" ? 1 : 0.3 }}
        >
          <div className="slip-head">
            <span className="slip-tag">{t.status === "open" ? "未回收" : "已回收"}</span>
            <span className="thread-actions">
              <button onClick={() => toggle(t)}>
                {t.status === "open" ? "回收" : "重新翻开"}
              </button>
              <button onClick={() => api.deleteForeshadowing(projectId, t.id).then(reload)}>
                删除
              </button>
            </span>
          </div>
          <p className="slip-body">
            <strong>{t.title}</strong>
            {t.content && (
              <>
                <br />
                {t.content}
              </>
            )}
          </p>
        </div>
      ))}
    </div>
  );
}

/* ---------- 行文 ---------- */

function IdiomsPane() {
  const pane = usePane(async (q) => (await api.suggestIdioms(q)).suggestions);
  return (
    <div className="pane">
      <AskForm pane={pane} placeholder="描述想形容的画面" action="找词" />
      {pane.error && <p className="error">{pane.error}</p>}
      {pane.loading && <p className="loading">在成语库里挑选…</p>}
      {pane.items && pane.items.length === 0 && (
        <p className="empty">成语库还是空的。先运行 import_idioms.py 灌入数据。</p>
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

const QUOTE_CATEGORIES = [
  "诗歌", "戏剧", "散文", "志怪文学",
  "爱情文学", "战争文学", "现实文学", "哲学", "成长文学",
];

const LIBRARIES = [
  { value: "", label: "双库" },
  { value: "素材", label: "素材库" },
  { value: "金句", label: "金句库" },
];

function QuotesPane() {
  const [category, setCategory] = useState("");
  const [library, setLibrary] = useState("");
  const pane = usePane(
    async (q) => (await api.literaryQuotes(q, category, library)).quotes
  );
  return (
    <div className="pane">
      <AskForm pane={pane} placeholder="当前情节的主题，如：爱情与想象" action="引经" />
      <div className="library-toggle" role="radiogroup" aria-label="选择检索库">
        {LIBRARIES.map((l) => (
          <button
            key={l.value}
            role="radio"
            aria-checked={library === l.value}
            className={library === l.value ? "active" : ""}
            onClick={() => setLibrary(l.value)}
          >
            {l.label}
          </button>
        ))}
      </div>
      <select
        className="category-filter"
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        aria-label="按分类过滤"
      >
        <option value="">全部分类</option>
        {QUOTE_CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      {pane.error && <p className="error">{pane.error}</p>}
      {pane.loading && <p className="loading">在文学库里检索…</p>}
      {pane.items && pane.items.length === 0 && (
        <p className="empty">这个分类下没有匹配的知识。换个分类或主题试试。</p>
      )}
      {pane.items?.map((qt, i) => (
        <div className="slip" key={i} style={{ "--slip-heat": Math.max(qt.score, 0.25) }}>
          <div className="slip-head">
            <span className="slip-tag">
              {qt.category ? `${qt.category}·` : ""}{qt.knowledge_type}
            </span>
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
          输入主题，检索文学知识——金句库只出公有领域原文，素材库供情节化用。
        </p>
      )}
    </div>
  );
}

/* ---------- 创作 ---------- */

function BranchesPane({ projectId, chapter }) {
  const pane = usePane(async (q) => {
    if (!chapter) throw new Error("先选择一个章节");
    const resp = await api.breakthrough(projectId, chapter.id, q);
    return resp.branches.map((b) => ({ ...b, clues: resp.clues }));
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
      {pane.items?.length > 0 && pane.items[0].clues?.length > 0 && (
        <p className="pane-hint">
          依据：{pane.items[0].clues.map((c) => c.content.slice(0, 10)).join(" / ")}
        </p>
      )}
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

function ImitatePane({ projectId, chapter, onAppend }) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);

  const accept = async () => {
    if (!result) return;
    const passed = result.attempts.some((a) => a.passed);
    await onAppend?.(result.text);
    if (passed) {
      // 过检稿内化为文风样本：正式续写将优先以它为语感参照，
      // 逐步取代对源素材（epub 样本）的直接依赖
      try {
        await api.addStyleSample(projectId, result.text, "内化");
        setNote("已并入正文，并内化为文风样本（续写将优先参照你的过检稿）。");
      } catch (err) {
        setNote(`已并入正文；内化失败：${err.message}`);
      }
    } else {
      setNote("已并入正文。此稿未过检，不作内化。");
    }
    setResult(null);
  };

  const run = async (revision = false) => {
    if (!chapter) {
      setError("先选择一个章节");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = {
        chapter_id: chapter.id,
        instruction: instruction.trim() || null,
        max_attempts: 2,
      };
      if (revision && result) {
        payload.previous_draft = result.text;
        payload.feedback = feedback.trim();
      }
      setResult(await api.imitate(projectId, payload));
      setFeedback("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pane">
      <p className="pane-hint">
        仿写走<strong>自检环</strong>：生成 → 异模型裁判 + 复述检测 → 不合格自动重写。
        每稿都带评分报告，较慢（1~3 分钟）但有据可依。
      </p>
      <textarea
        className="ingest-text"
        rows={2}
        value={instruction}
        placeholder="方向指引，如：写陆沉赶到医院，150字左右"
        onChange={(e) => setInstruction(e.target.value)}
      />
      <div className="ingest-actions">
        <button className="btn primary" onClick={() => run(false)} disabled={busy}>
          {busy ? "自检环运行中…" : "开始仿写"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {note && <p className="ok">{note}</p>}

      {result && (
        <>
          <div className="imitate-report">
            {result.attempts.map((a) => (
              <div className="attempt" key={a.attempt}>
                <span className={a.passed ? "ok" : "warn"}>
                  第{a.attempt}稿 {a.passed ? "✓过检" : "未过检"}
                </span>
                <span>文风 {a.style_score}/10</span>
                <span>AI味 {a.ai_flavor}/10</span>
                <span>复述 {(a.ngram_overlap * 100).toFixed(1)}%</span>
              </div>
            ))}
            {result.attempts.at(-1)?.notes && (
              <p className="pane-hint">裁判批语：{result.attempts.at(-1).notes}</p>
            )}
          </div>
          <div className="imitate-draft">{result.text}</div>
          <div className="ingest-actions">
            <button className="btn primary" onClick={accept}>
              并入正文
            </button>
            <button className="btn ghost" onClick={() => setResult(null)}>
              弃稿
            </button>
          </div>
          <form
            className="ask"
            onSubmit={(e) => {
              e.preventDefault();
              if (feedback.trim()) run(true);
            }}
          >
            <input
              value={feedback}
              placeholder="不满意？写下修改意见让它重写"
              onChange={(e) => setFeedback(e.target.value)}
            />
            <button className="btn ghost" type="submit" disabled={busy || !feedback.trim()}>
              修订
            </button>
          </form>
        </>
      )}
    </div>
  );
}
