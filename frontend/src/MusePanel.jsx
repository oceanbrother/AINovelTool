import React, { useEffect, useState } from "react";
import { api, streamImitate, streamRefineWrite } from "./api.js";

// Three sections, each with focused windows:
//   架构 — the static library: material ingest, settings, threads
//   行文 — the sentence level: citations, idioms
//   创作 — the generation pipeline: 破壁(diverge) → 细纲(stage) → 仿写(write, vetted)
const SECTIONS = [
  {
    key: "arch",
    label: "架构",
    tabs: [
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
      { key: "outline", label: "细纲" },
      { key: "imitate", label: "仿写" },
      { key: "refine", label: "精修" },
    ],
  },
];

export default function MusePanel({
  projectId,
  chapter,
  onAppend,
  onDirective,
  directive,
  directiveNonce,
}) {
  const [sectionKey, setSectionKey] = useState("arch");
  const section = SECTIONS.find((s) => s.key === sectionKey);
  const [tabKey, setTabKey] = useState(section.tabs[0].key);

  const switchSection = (key) => {
    setSectionKey(key);
    setTabKey(SECTIONS.find((s) => s.key === key).tabs[0].key);
  };

  // 细纲 → 仿写 handoff: prefill the directive and jump to the 仿写 tab
  const useForImitate = (text) => {
    onDirective?.(text);
    setSectionKey("create");
    setTabKey("imitate");
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
      {tabKey === "ingest" && <IngestPane projectId={projectId} />}
      {tabKey === "settings" && <SettingsPane projectId={projectId} />}
      {tabKey === "threads" && <ThreadsPane projectId={projectId} chapter={chapter} />}
      {tabKey === "quotes" && <QuotesPane />}
      {tabKey === "idioms" && <IdiomsPane />}
      {tabKey === "branches" && <BranchesPane projectId={projectId} chapter={chapter} />}
      {tabKey === "outline" && (
        <OutlinePane
          projectId={projectId}
          chapter={chapter}
          onContinue={onDirective}
          onImitate={useForImitate}
        />
      )}
      {tabKey === "imitate" && (
        <ImitatePane
          projectId={projectId}
          chapter={chapter}
          onAppend={onAppend}
          directive={directive}
          directiveNonce={directiveNonce}
        />
      )}
      {tabKey === "refine" && (
        <RefinePane projectId={projectId} chapter={chapter} onAppend={onAppend} />
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

/* ---------- 创作 · 细纲 ---------- */

function OutlinePane({ projectId, chapter, onContinue, onImitate }) {
  const [fragment, setFragment] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [edited, setEdited] = useState({}); // index -> author-edited directive
  const [sentHint, setSentHint] = useState(false);

  const run = async () => {
    if (fragment.trim().length < 10) {
      setError("给我一段正文（至少十个字），而不是一句概括。");
      return;
    }
    setLoading(true);
    setError(null);
    setSentHint(false);
    try {
      setResult(await api.composeOutline(projectId, fragment.trim(), 2));
      setEdited({});
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const useChapterTail = () => {
    if (chapter?.content) setFragment(chapter.content.slice(-300));
  };

  const compile = (o) =>
    `走向：${o.direction}\n视角：${o.pov}\n入场：${o.entrances}\n` +
    `设定引出：${o.reveals}\n节拍：\n` +
    o.beats.map((b, i) => `${i + 1}. ${b}`).join("\n");

  const directiveOf = (i, o) => (i in edited ? edited[i] : compile(o));

  return (
    <div className="pane">
      <p className="pane-hint">
        已经知道接下来大概往哪走时，来这里<strong>排布局</strong>：生成几条可编辑的
        执行细纲（视角调度 / 角色入场 / 设定引出 / 节拍）。改好后 → 续写或 → 仿写生成成稿。
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
          {loading ? "排布中…" : "生成细纲"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {sentHint && (
        <p className="ok">已填入「往下写」的方向指引——回到稿纸点『往下写』即可生成。</p>
      )}

      {result?.options.map((o, i) => (
        <div className="outline-card" key={i}>
          <div className="outline-dir">{o.direction}</div>
          <dl className="outline-fields">
            <div><dt>视角</dt><dd>{o.pov}</dd></div>
            <div><dt>入场</dt><dd>{o.entrances}</dd></div>
            <div><dt>设定引出</dt><dd>{o.reveals}</dd></div>
          </dl>
          {o.beats.length > 0 && (
            <ol className="outline-beats">
              {o.beats.map((b, j) => <li key={j}>{b}</li>)}
            </ol>
          )}
          {o.grounded.length > 0 && (
            <div className="clue-strip" aria-label="细纲依据的设定">
              <span className="clue-strip-label">依据</span>
              {o.grounded.map((g, j) => (
                <span className="clue-chip" key={j} title={g}>{g.slice(0, 14)}</span>
              ))}
            </div>
          )}
          <textarea
            className="outline-edit"
            rows={5}
            value={directiveOf(i, o)}
            onChange={(e) => setEdited({ ...edited, [i]: e.target.value })}
          />
          <div className="ingest-actions">
            <button
              className="btn ghost"
              onClick={() => {
                onContinue?.(directiveOf(i, o));
                setSentHint(true);
              }}
            >
              → 续写
            </button>
            <button className="btn primary" onClick={() => onImitate?.(directiveOf(i, o))}>
              → 仿写
            </button>
          </div>
        </div>
      ))}

      {result && (
        <details className="debug-view">
          <summary>依据：原始检索命中</summary>
          {result.raw_settings.map((c) => (
            <div className="slip" key={c.id} style={{ "--slip-heat": 0.3 }}>
              <div className="slip-head">
                <span className="slip-tag">{SOURCE_LABEL[c.source_type] || c.source_type}</span>
                <span className="slip-score">{c.score.toFixed(3)}</span>
              </div>
              <p className="slip-body">{c.content}</p>
            </div>
          ))}
        </details>
      )}
      {!result && !loading && (
        <p className="empty">
          破壁找到方向后，来这里把它排成可执行的细纲。
          <br />
          每条细纲都能改，改好交给续写或仿写写成稿。
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

const LABEL_NAME = { epub: "原著", manual: "手贴", 内化: "内化" };
const PAGE_SIZE = 20;

function SampleSlip({ projectId, sample, onDelete }) {
  const [open, setOpen] = useState(false);
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const expand = async () => {
    if (idea.trim().length < 4) {
      setError("先写一句当前构思。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await api.expandSample(projectId, sample.id, idea.trim()));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="slip" style={{ "--slip-heat": 0.4 }}>
      <div className="slip-head">
        <span className="slip-tag">
          {LABEL_NAME[sample.source_label] || sample.source_label || "样本"}
          {sample.scene_tag ? ` · ${sample.scene_tag}` : ""}
        </span>
        <span className="thread-actions">
          <button onClick={() => setOpen((v) => !v)}>{open ? "收起" : "扩写"}</button>
          <button onClick={() => onDelete(sample.id)}>删除</button>
        </span>
      </div>
      <p className="slip-body">{sample.content.slice(0, 90)}…</p>
      {open && (
        <div className="expand-box">
          <input
            value={idea}
            placeholder="当前构思，如：写主角初见神秘女孩的一刻"
            onChange={(e) => setIdea(e.target.value)}
          />
          <button className="btn ghost" onClick={expand} disabled={busy}>
            {busy ? "扩写中…" : "借这段的手法扩写"}
          </button>
          {error && <p className="error">{error}</p>}
          {result && (
            <>
              <div className="expand-result">{result.text}</div>
              <p className="pane-hint">
                复述率 {(result.ngram_overlap * 100).toFixed(1)}%
                （越低越好——只借手法与语感，未抄原文）
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function IngestPane({ projectId }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const [data, setData] = useState(null); // {total, items, by_label, by_scene}
  const [labelFilter, setLabelFilter] = useState("");
  const [sceneFilter, setSceneFilter] = useState("");
  const [offset, setOffset] = useState(0);

  const reload = async () => {
    setData(
      await api.listStyleSamples(projectId, {
        label: labelFilter,
        scene: sceneFilter,
        offset,
        limit: PAGE_SIZE,
      })
    );
  };
  useEffect(() => {
    reload().catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, labelFilter, sceneFilter, offset]);

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
      setOffset(0);
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    await api.deleteStyleSample(projectId, id);
    await reload();
  };

  const total = data?.total ?? 0;
  const grandTotal = data
    ? Object.values(data.by_label).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div className="pane">
      <p className="pane-hint">
        粘贴文字或选择 .txt 文件，自动切块进入<strong>私有文风库</strong>——
        仿写与续写会从这里召回语感。整本 epub 用后端脚本导入。
      </p>
      <textarea
        className="ingest-text"
        rows={5}
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

      {data && (
        <>
          <h3 className="pane-title">文风库 · {grandTotal} 段</h3>

          <div className="facet-row">
            <button
              className={`chip${labelFilter === "" ? " active" : ""}`}
              onClick={() => {
                setLabelFilter("");
                setOffset(0);
              }}
            >
              全部来源
            </button>
            {Object.entries(data.by_label).map(([k, n]) => (
              <button
                key={k}
                className={`chip${labelFilter === k ? " active" : ""}`}
                onClick={() => {
                  setLabelFilter(labelFilter === k ? "" : k);
                  setOffset(0);
                }}
              >
                {LABEL_NAME[k] || k} {n}
              </button>
            ))}
          </div>

          <div className="facet-row">
            <button
              className={`chip${sceneFilter === "" ? " active" : ""}`}
              onClick={() => {
                setSceneFilter("");
                setOffset(0);
              }}
            >
              全部场景
            </button>
            {Object.entries(data.by_scene).map(([k, n]) => (
              <button
                key={k}
                className={`chip${sceneFilter === k ? " active" : ""}`}
                onClick={() => {
                  setSceneFilter(sceneFilter === k ? "" : k);
                  setOffset(0);
                }}
              >
                {k} {n}
              </button>
            ))}
          </div>

          {data.items.length === 0 && (
            <p className="empty">这个筛选下没有样本。</p>
          )}
          {data.items.map((s) => (
            <SampleSlip key={s.id} projectId={projectId} sample={s} onDelete={remove} />
          ))}

          {total > PAGE_SIZE && (
            <div className="pager">
              <button
                className="btn ghost"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                上一页
              </button>
              <span className="pager-info">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
              </span>
              <button
                className="btn ghost"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一页
              </button>
            </div>
          )}
        </>
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
        <p className="empty">没有匹配的成语。换一种画面描述再试试。</p>
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
        <div className="clue-strip" aria-label="分支依据的设定">
          <span className="clue-strip-label">依据</span>
          {pane.items[0].clues.map((c, i) => (
            <span className="clue-chip" key={i} title={c.content}>
              {c.content.slice(0, 14)}
            </span>
          ))}
        </div>
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

function ImitatePane({ projectId, chapter, onAppend, directive, directiveNonce }) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);
  const [stage, setStage] = useState(null); // current SSE phase during a run
  const [liveAttempts, setLiveAttempts] = useState([]); // scorecards as they land
  const [hero, setHero] = useState("主角"); // sample name for the placeholder
  // the author's working copy; result.text stays as the model's original so the
  // pair can be recorded on accept
  const [draft, setDraft] = useState("");

  useEffect(() => {
    api
      .listCharacters(projectId)
      .then((cs) => cs[0] && setHero(cs[0].name))
      .catch(() => {});
  }, [projectId]);

  // 细纲 → 仿写 handoff: prefill the instruction when a directive is handed in
  useEffect(() => {
    if (directive) setInstruction(directive);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [directiveNonce]);

  const accept = async () => {
    if (!result) return;
    const passed = result.attempts.some((a) => a.passed);
    await onAppend?.(draft);
    // 记录 (模型原稿, 你并入的版本)。内化规则在后端，避免前后端两套判断走岔。
    // 内化的是**你的版本**——你动过手的字才算你的语感。
    try {
      const rec = await api.recordOverride(projectId, {
        source: "imitate",
        suggested_text: result.text,
        accepted_text: draft,
        chapter_id: chapter?.id ?? null,
        passed_check: passed,
      });
      const edited = rec.edit_ratio > 0.001;
      setNote(
        rec.internalized
          ? `已并入正文，并内化为文风样本${edited ? "（存的是你改后的版本）" : ""}。`
          : "已并入正文。此稿未过检且你未修改，不作内化。"
      );
    } catch (err) {
      setNote(`已并入正文；记录失败：${err.message}`);
    }
    setResult(null);
    setDraft("");
  };

  const run = async (revision = false) => {
    if (!chapter) {
      setError("先选择一个章节");
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    setStage("正在启动自检环…");
    setLiveAttempts([]);
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
      setResult(null);
      const final = await streamImitate(projectId, payload, {
        onStage: (s) => setStage(s),
        onAttempt: (a) => setLiveAttempts((prev) => [...prev, a]),
      });
      setResult(final);
      setDraft(final?.text || ""); // working copy the author can revise in place
      setFeedback("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      setStage(null);
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
        placeholder={`方向指引，如：写${hero}赶到现场，150字左右`}
        onChange={(e) => setInstruction(e.target.value)}
      />
      <div className="ingest-actions">
        <button className="btn primary" onClick={() => run(false)} disabled={busy}>
          {busy ? "自检环运行中…" : "开始仿写"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {note && <p className="ok">{note}</p>}

      {busy && (
        <div className="imitate-progress">
          <div className="stage-line">
            <span className="stage-dot" />
            {stage}
          </div>
          {liveAttempts.map((a) => (
            <div className="attempt" key={a.attempt}>
              <span className={a.passed ? "ok" : "warn"}>
                第{a.attempt}稿 {a.passed ? "✓过检" : "未过检"}
              </span>
              <span>文风 {a.style_score}/10</span>
              <span>AI味 {a.ai_flavor}/10</span>
              <span>复述 {(a.ngram_overlap * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      )}

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
          {/* editable before merging — the only moment the model's version and
              yours are still separable */}
          <textarea
            className="imitate-draft editable"
            value={draft}
            aria-label="生成的稿件，可直接修改后再并入"
            onChange={(e) => setDraft(e.target.value)}
          />
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

/* ---------- 创作 · 精修 ---------- */
// The precision loop: multi-candidate → pick/merge → editable ScenePlan →
// plan-conditioned write with a constraint-verified rewrite loop. Two author
// decision points (pick a candidate, edit the plan) split it into three calls.

const PLAN_FIELDS = [
  ["goal", "本场目标"],
  ["desire", "角色欲望"],
  ["conflict", "冲突"],
  ["info_shift", "信息变化"],
  ["emotion_curve", "情绪曲线"],
  ["end_state", "结尾状态"],
];

function RefinePane({ projectId, chapter, onAppend }) {
  const [fragment, setFragment] = useState("");
  const [candidates, setCandidates] = useState(null); // ① options
  const [picked, setPicked] = useState({}); // index -> bool (merge set)
  const [plan, setPlan] = useState(null); // ② editable ScenePlan
  const [result, setResult] = useState(null); // ③ final draft + report
  // author's working copy; result.text stays as the model's original so the
  // (suggested, kept) pair can be recorded on accept
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(null);
  const [liveAttempts, setLiveAttempts] = useState([]);
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);

  const useChapterTail = () => {
    if (chapter?.content) setFragment(chapter.content.slice(-300));
  };

  // ① 候选
  const genCandidates = async () => {
    if (fragment.trim().length < 10) {
      setError("给我一段正文（至少十个字），而不是一句概括。");
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const resp = await api.refineCandidates(projectId, fragment.trim(), 4);
      setCandidates(resp.candidates);
      setPicked({});
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const toggle = (i) => setPicked((p) => ({ ...p, [i]: !p[i] }));

  // merge selected candidates client-side (author "把两个候选组合起来")
  const mergeSelected = () => {
    const sel = candidates.filter((_, i) => picked[i]);
    if (sel.length === 0) return null;
    if (sel.length === 1) return sel[0];
    const join = (k) => [...new Set(sel.map((c) => c[k]).filter(Boolean))].join(" ／ ");
    return {
      summary: sel.map((c) => c.summary).join("；并且，"),
      conflict_source: join("conflict_source"),
      agency: join("agency"),
      reveal_order: join("reveal_order"),
      emotion_arc: join("emotion_arc"),
      turn: join("turn"),
      open_question: join("open_question"),
      refs: [...new Set(sel.flatMap((c) => c.refs))],
      grounded: [...new Set(sel.flatMap((c) => c.grounded))],
      repetition: 0,
      repetition_flag: false,
    };
  };

  // ② 场景计划
  const expandPlan = async () => {
    const candidate = mergeSelected();
    if (!candidate) {
      setError("先勾选至少一条候选。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await api.refinePlan(projectId, fragment.trim(), candidate);
      setPlan(resp.plan);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const setField = (k, v) => setPlan((p) => ({ ...p, [k]: v }));
  const setList = (k, text) =>
    setPlan((p) => ({
      ...p,
      [k]: text.split("\n").map((s) => s.trim()).filter(Boolean),
    }));

  // ③ 校验写作
  const write = async () => {
    if (!chapter) {
      setError("先选择一个章节");
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    setStage("正在启动校验写循环…");
    setLiveAttempts([]);
    try {
      const final = await streamRefineWrite(
        projectId,
        { chapter_id: chapter.id, plan, instruction: null, max_attempts: 2 },
        {
          onStage: (s) => setStage(s),
          onAttempt: (a) => setLiveAttempts((prev) => [...prev, a]),
        }
      );
      setResult(final);
      setDraft(final?.text || ""); // working copy the author can revise in place
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      setStage(null);
    }
  };

  const accept = async () => {
    if (!result) return;
    const satisfied = result.attempts?.at(-1)?.satisfied ?? false;
    await onAppend?.(draft);
    // 记录 (模型原稿, 你并入的版本)。以前精修稿一律不内化——理由是它按"约束达标"
    // 过检、不算语感范本；但你亲手改过的字就是你的语感，所以改用同一条规则：
    // 动过手 → 内化你的版本。判定在后端，前后端不会走岔。
    try {
      const rec = await api.recordOverride(projectId, {
        source: "refine",
        suggested_text: result.text,
        accepted_text: draft,
        chapter_id: chapter?.id ?? null,
        passed_check: satisfied,
      });
      setNote(
        rec.internalized
          ? `已并入正文，并把${rec.edit_ratio > 0.001 ? "你改后的" : "该"}版本内化为文风样本。`
          : "已并入正文。"
      );
    } catch (err) {
      setNote(`已并入正文；记录失败：${err.message}`);
    }
    setResult(null);
    setDraft("");
    setPlan(null);
    setCandidates(null);
  };

  return (
    <div className="pane">
      <p className="pane-hint">
        <strong>精修</strong>：多候选走向 → 选 / 合并 → 场景计划（必须出现 / 不能发生）
        → 依计划生成 → <strong>逐条核对约束</strong>，不达标自动重写。最慢也最稳，出精稿。
      </p>

      {/* ① 片段输入 */}
      {!candidates && !plan && !result && (
        <>
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
            <button className="btn primary" onClick={genCandidates} disabled={busy}>
              {busy ? "构思中…" : "生成候选走向"}
            </button>
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
      {note && <p className="ok">{note}</p>}

      {/* ① 候选列表（勾选可多选合并） */}
      {candidates && !plan && !result && (
        <>
          {candidates.length === 0 && <p className="warn">没解析出候选，换段文字再试。</p>}
          {candidates.map((c, i) => (
            <label className={`refine-cand${picked[i] ? " picked" : ""}`} key={i}>
              <input type="checkbox" checked={!!picked[i]} onChange={() => toggle(i)} />
              <div className="refine-cand-body">
                <div className="refine-cand-sum">
                  {c.summary}
                  {c.repetition_flag && (
                    <span className="warn" title={`与已有章节相似度 ${c.repetition}`}>
                      　· 疑似重复
                    </span>
                  )}
                </div>
                <dl className="outline-fields">
                  <div><dt>冲突来源</dt><dd>{c.conflict_source}</dd></div>
                  <div><dt>主/被动</dt><dd>{c.agency}</dd></div>
                  <div><dt>揭示序</dt><dd>{c.reveal_order}</dd></div>
                  <div><dt>情绪</dt><dd>{c.emotion_arc}</dd></div>
                  <div><dt>转折</dt><dd>{c.turn}</dd></div>
                  <div><dt>悬念</dt><dd>{c.open_question}</dd></div>
                </dl>
              </div>
            </label>
          ))}
          <div className="ingest-actions">
            <button
              className="btn ghost"
              onClick={() => {
                setCandidates(null);
                setPicked({});
              }}
            >
              重来
            </button>
            <button className="btn primary" onClick={expandPlan} disabled={busy}>
              {busy ? "排布中…" : "选中项 → 场景计划"}
            </button>
          </div>
        </>
      )}

      {/* ② 场景计划编辑 */}
      {plan && !result && (
        <div className="refine-plan">
          {plan.scene_tag && <span className="slip-tag">场景：{plan.scene_tag}</span>}
          {PLAN_FIELDS.map(([k, label]) => (
            <label className="refine-field" key={k}>
              <span>{label}</span>
              <textarea
                rows={1}
                value={plan[k] || ""}
                onChange={(e) => setField(k, e.target.value)}
              />
            </label>
          ))}
          <label className="refine-field">
            <span>必须出现（每行一条，会逐条核对）</span>
            <textarea
              rows={3}
              value={(plan.must_include || []).join("\n")}
              onChange={(e) => setList("must_include", e.target.value)}
            />
          </label>
          <label className="refine-field">
            <span>不能发生（每行一条，会逐条核对）</span>
            <textarea
              rows={2}
              value={(plan.must_not || []).join("\n")}
              onChange={(e) => setList("must_not", e.target.value)}
            />
          </label>
          <div className="ingest-actions">
            <button className="btn ghost" onClick={() => setPlan(null)} disabled={busy}>
              ← 重选候选
            </button>
            <button className="btn primary" onClick={write} disabled={busy}>
              {busy ? "校验写循环运行中…" : "→ 生成成稿"}
            </button>
          </div>
        </div>
      )}

      {/* ③ 进度 */}
      {busy && stage && (
        <div className="imitate-progress">
          <div className="stage-line">
            <span className="stage-dot" />
            {stage}
          </div>
          {liveAttempts.map((a) => (
            <div className="attempt" key={a.attempt}>
              <span className={a.satisfied ? "ok" : "warn"}>
                第{a.attempt}稿 {a.satisfied ? "✓达标" : "未达标"}
              </span>
              <span>
                约束 {a.checks.filter((k) => k.satisfied).length}/{a.checks.length}
              </span>
              <span>复述 {(a.ngram_overlap * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      )}

      {/* ③ 成稿 + 逐条核对 */}
      {result && (
        <>
          <div className="imitate-report">
            {result.attempts.map((a) => (
              <div className="attempt-block" key={a.attempt}>
                <div className="attempt">
                  <span className={a.satisfied ? "ok" : "warn"}>
                    第{a.attempt}稿 {a.satisfied ? "✓达标" : "未达标"}
                  </span>
                  <span>复述 {(a.ngram_overlap * 100).toFixed(1)}%</span>
                </div>
                {a.checks.length > 0 && (
                  <ul className="refine-checks">
                    {a.checks.map((k, j) => (
                      <li key={j} className={k.satisfied ? "ok" : "warn"}>
                        {k.satisfied ? "✓" : "✗"} {k.kind === "include" ? "必须" : "不能"}：
                        {k.text}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
          {/* editable before merging — the only moment the model's version and
              yours are still separable */}
          <textarea
            className="imitate-draft editable"
            value={draft}
            aria-label="生成的稿件，可直接修改后再并入"
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="ingest-actions">
            <button className="btn primary" onClick={accept}>
              并入正文
            </button>
            <button className="btn ghost" onClick={() => setResult(null)}>
              回到计划
            </button>
          </div>
        </>
      )}

      {!candidates && !plan && !result && !busy && (
        <p className="empty">
          精修是最重的模式：
          <br />
          给一段正文，拿到几条差异化走向，挑一条排成带约束的场景计划，
          再让它按计划写、逐条核对约束。
        </p>
      )}
    </div>
  );
}
