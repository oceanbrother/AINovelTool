import React, { useEffect, useState } from "react";
import { api, streamImitate, streamRefineWrite } from "./api.js";

// Three sections, each with focused windows:
//   架构 — the static library: material ingest, settings, clues
//   行文 — the sentence level: citations, idioms
//   创作 — two ways to write: 精修(plan then verify) · 仿写(voice only)
//
// This used to be ten tabs. 破壁 and 细纲 were folded into 精修, whose candidate
// and plan stages already do both jobs and do them with checkable constraints;
// 伏笔 and 知识 became one 线索 card, because a thread IS a withheld fact and
// registering the same story element twice let the two drift apart.
const SECTIONS = [
  {
    key: "arch",
    label: "架构",
    tabs: [
      { key: "ingest", label: "素材" },
      { key: "settings", label: "设定" },
      { key: "clues", label: "线索" },
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
      { key: "refine", label: "精修" },
      { key: "imitate", label: "仿写" },
    ],
  },
];

export default function MusePanel({
  projectId,
  chapter,
  chapters = [],
  onAppend,
  onDirective,
  directive,
  directiveNonce,
}) {
  const [sectionKey, setSectionKey] = useState("arch");
  const section = SECTIONS.find((s) => s.key === sectionKey);
  const [tabKey, setTabKey] = useState(section.tabs[0].key);
  // 调校不是第四个版块。它改的是工具怎么说话，不是这本书写什么——
  // 做成对等页签会把一个设置面板混进创作动线里。
  const [tuning, setTuning] = useState(false);
  // 拆书同理，而且更远：它处理的是别人的书，跨项目共用，跟当前这一章无关。
  // 两个开关互斥——同时打开两个接管式面板没有意义。
  const [decon, setDecon] = useState(false);

  const switchSection = (key) => {
    setSectionKey(key);
    setTabKey(SECTIONS.find((s) => s.key === key).tabs[0].key);
  };

  // 精修 → 仿写 handoff: prefill the directive and jump to the 仿写 tab
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
        <span className="spacer" />
        <button
          className={`tuning-btn${decon ? " active" : ""}`}
          title="拆书：把一本参考作品标成金标准（跨项目，结果留在本机）"
          aria-pressed={decon}
          onClick={() => {
            setDecon((v) => !v);
            setTuning(false);
          }}
        >
          拆书
        </button>
        <button
          className={`tuning-btn${tuning ? " active" : ""}`}
          title="调校：查看并修改工具发出的提示词"
          aria-pressed={tuning}
          onClick={() => {
            setTuning((v) => !v);
            setDecon(false);
          }}
        >
          调校
        </button>
      </div>
      {decon ? (
        <DeconstructPane onClose={() => setDecon(false)} />
      ) : tuning ? (
        <PromptsPane onClose={() => setTuning(false)} />
      ) : (
        <>
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
      {tabKey === "clues" && (
        <CluesPane projectId={projectId} chapter={chapter} chapters={chapters} />
      )}
      {tabKey === "quotes" && <QuotesPane />}
      {tabKey === "idioms" && <IdiomsPane />}
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
        <RefinePane
          projectId={projectId}
          chapter={chapter}
          onAppend={onAppend}
          onContinue={onDirective}
          onImitate={useForImitate}
        />
      )}
        </>
      )}
    </aside>
  );
}

// 拆书面板：把参考作品一场一场标成金标准。
//
// 为什么值得做一个界面：这批标注的瓶颈是作者的分钟数，不是算法。功能标签闸门
// 已经两次未过，两次都是因为少数类样本太少（转折 2 条、回收 2 条，无法判定）。
// 命令行脚本打印 300 段读 stdin，没人标得完，而标不完的金标准一文不值。
//
// 为什么是随机而不是分层：分层需要一个能把转折捞出来的候选器。写过两个
// （罕见词长程复现 / 纹理断点），拿仅有的真金标准一验，转折通道 67% 百分位——
// 比随机还差。负结果记在 services/deconstruct.py 里。随机更费作者时间，但换来
// 一个能解释的准确率和 kappa。
//
// 三条不能松的：
// · 盲标。不给模型猜测，不给通道来源，也不给已标各类的计数——作者看见自己连答
//   了四十个「信息」，就会开始找理由答别的，闸门量到的就成了那个漂移。
// · 跳过要记账。判不了的场景硬标是在制造噪声；但静默丢弃更糟——30% 的跳过率
//   本身就是关于分类学的发现。
// · 键盘优先。1/2/3/4 打标签，0 跳过，全程不用碰鼠标。
function DeconstructPane({ onClose }) {
  const [works, setWorks] = useState([]);
  const [work, setWork] = useState("");
  const [taxonomy, setTaxonomy] = useState([]);
  const [item, setItem] = useState(null);
  const [prog, setProg] = useState(null);
  const [done, setDone] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.listCorpora(), api.labelTaxonomy()])
      .then(([w, t]) => {
        setWorks(w);
        setTaxonomy(t);
        const first = w.find((x) => x.built) || w[0];
        if (first) setWork(first.work);
      })
      .catch((e) => setErr(String(e.message || e)));
  }, []);

  const pull = (w) =>
    api
      .nextToLabel(w)
      .then((r) => {
        setDone(r.done);
        setItem(r.done ? null : r.item);
        setProg(r);
        setReason("");
      })
      .catch((e) => setErr(String(e.message || e)));

  // 只由 work 触发。
  //
  // 曾经这里依赖 [work, works]，而 pull() 里又 setWorks(...) 去同步下拉框的
  // 计数——map 每次返回新数组，引用一变就重新触发本 effect，再 pull，再
  // setWorks，自激。实测 665,781 次 GET /next 对 153 次 POST /label（每存一条
  // 打约 4,350 次请求），每个响应带一整场正文，标注到第 150 条时标签页耗尽内存。
  //
  // 当时那个改动是视觉验过的：计数确实同步了。单次交互看不见循环，只有累计请求
  // 数看得见——所以这类改动之后要数请求，不是看画面。
  useEffect(() => {
    if (work) pull(work);
  }, [work]);

  const start = () => {
    setBusy(true);
    setErr("");
    api
      .buildLabelQueue(work, 300, 0)
      .then((p) => {
        setProg(p);
        return pull(work);
      })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setBusy(false));
  };

  const send = (label) => {
    if (!item || busy) return;
    setBusy(true);
    setErr("");
    api
      .saveLabel(work, item.id, label, reason.trim())
      .then(() => pull(work))
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setBusy(false));
  };

  // 数字键直达。输入理由时不劫持按键——那里要能打字。
  useEffect(() => {
    const onKey = (e) => {
      if (!item || busy) return;
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      const i = "1234".indexOf(e.key);
      if (i >= 0 && taxonomy[i]) send(taxonomy[i].name);
      else if (e.key === "0") send("跳过");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, busy, taxonomy, reason, work]);

  // prog 是唯一权威：它每次 pull 都刷新。works 只在挂载时取一次，用来填下拉框，
  // 之后不再更新——它一更新就会和上面那个 effect 形成回路。
  const built = prog?.built ?? works.find((x) => x.work === work)?.built;
  const pct = prog?.total ? Math.round((prog.seen / prog.total) * 100) : 0;

  return (
    <div className="pane decon-pane">
      <header className="pane-head">
        拆书
        <span className="muted">
          把一本你在学的书标成金标准 · 结果留在本机
        </span>
        <button className="ghost" onClick={onClose}>
          收起
        </button>
      </header>

      {err && <p className="err">{err}</p>}

      <div className="decon-bar">
        <select value={work} onChange={(e) => setWork(e.target.value)}>
          {works.map((w) => {
            // 选中那一项读 prog（实时），其余读挂载时的快照。两处都显示会不同步，
            // 而"下拉说 0/300、进度条说 151/300"看起来就像刚才那一下没存上。
            const p = w.work === work && prog?.built ? prog : w;
            return (
              <option key={w.work} value={w.work}>
                {w.work}
                {p.built ? ` · ${p.seen}/${p.total}` : " · 未开始"}
              </option>
            );
          })}
        </select>
        {!built && (
          <button className="primary" disabled={!work || busy} onClick={start}>
            随机抽 300 场开始
          </button>
        )}
        {prog?.built && (
          <span className="decon-prog" title={prog.gold_file}>
            <i style={{ width: `${pct}%` }} />
            <b>
              {prog.seen}/{prog.total}
            </b>
            {prog.skipped > 0 && <em>跳过 {prog.skipped}</em>}
          </span>
        )}
      </div>

      {!built && (
        <p className="hint">
          随机抽样，不做分层。分层需要一个能把少数类捞出来的候选器，写过两个都没
          过验证（负结果见 <code>services/deconstruct.py</code>）。随机更费时间，
          但换来一个能解释的准确率。
        </p>
      )}

      {/* 队列没建时后端也回 done=true（没有待标项），不加 built 会显示"标完了" */}
      {done && built && (
        <p className="hint ok">
          这一批标完了。用 <code>eval/run_function_agreement.py --work {work}
          {" "}--gold ../{prog?.gold_file}</code> 过闸门。
        </p>
      )}

      {item && (
        <>
          <div className="decon-scene">
            {item.context_before && (
              <p className="decon-ctx">…{item.context_before}</p>
            )}
            <div className="decon-text">
              {item.text.split("\n").map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          </div>

          <div className="decon-choices">
            {taxonomy.map((t, i) => (
              <button key={t.name} disabled={busy} onClick={() => send(t.name)}>
                <kbd>{i + 1}</kbd>
                <b>{t.name}</b>
                <span>{t.meaning}</span>
                <em>{t.test}</em>
              </button>
            ))}
            <button className="skip" disabled={busy} onClick={() => send("跳过")}>
              <kbd>0</kbd>
              <b>判不了</b>
              <span>硬标是在制造噪声，跳过会被记账</span>
            </button>
          </div>

          <input
            className="decon-reason"
            placeholder="理由（可空）——判错时它是唯一能看出分类学哪里坏了的东西"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </>
      )}
    </div>
  );
}

// 调校面板：把工具发出的每一条指令摆出来，能改的让改，量具只给看。
//
// 为什么要有这个：五轮迭代买来的纠偏全是提示词文本——限制本场功能数量、goal
// 要写不可逆变化、声音通道不得动信息边界。它们全被编译进作者碰不到的字符串。
// 计划生成得不对时，作者唯一的办法是重roll。
//
// 为什么量具不给改：README 里每个数字（约束兑现 59%→93%、kappa 0.310、
// 两阶段 88.0% vs 72.6%）都是用那三个字符串测出来的。改一次，之后所有对比
// 都失去意义，而且没有任何迹象。后端那道锁是结构性的（那些函数不接 session），
// 这里只负责把理由说清楚。
function PromptsPane({ onClose }) {
  const [items, setItems] = useState([]);
  const [openKey, setOpenKey] = useState(null);
  const [drafts, setDrafts] = useState({}); // key -> 编辑中的文本
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = () =>
    api
      .listPrompts()
      .then(setItems)
      .catch((e) => setErr(String(e.message || e)));
  useEffect(() => {
    load();
  }, []);

  const bodyOf = (it) => (drafts[it.key] !== undefined ? drafts[it.key] : it.body);
  const dirty = (it) => bodyOf(it) !== it.body;

  const save = async (it) => {
    setBusy(true);
    setErr("");
    try {
      await api.savePrompt(it.key, bodyOf(it));
      setDrafts((d) => {
        const n = { ...d };
        delete n[it.key];
        return n;
      });
      await load();
    } catch (e) {
      // 422 带的是拒绝理由，作者需要看到原文
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async (it) => {
    setBusy(true);
    setErr("");
    try {
      await api.resetPrompt(it.key);
      setDrafts((d) => {
        const n = { ...d };
        delete n[it.key];
        return n;
      });
      await load();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const editable = items.filter((i) => i.editable);
  const locked = items.filter((i) => !i.editable);
  const nOverridden = editable.filter((i) => i.overridden).length;

  const row = (it) => {
    const open = openKey === it.key;
    const body = bodyOf(it);
    // 规则条数摊在面上：可编辑的提示词最典型的坏法不是改错一条，是无限追加，
    // 加到模型把所有条都当背景噪音。让它可见，作者才会自己删。
    const grew = it.rules - it.default_rules;
    return (
      <div className={`prompt-row${open ? " open" : ""}`} key={it.key}>
        <button
          className="prompt-head"
          onClick={() => setOpenKey(open ? null : it.key)}
        >
          <span className="prompt-label">
            {it.editable ? "" : "🔒 "}
            {it.label}
          </span>
          <span className="prompt-meta">
            <span className="prompt-key">{it.key}</span>
            <span className="chip">{it.rules} 条规则</span>
            {grew !== 0 && (
              <span className={grew > 0 ? "chip warn" : "chip ok"}>
                {grew > 0 ? `+${grew}` : grew}
              </span>
            )}
            {it.overridden && <span className="chip on">已改 ×{it.revision}</span>}
            {it.stale_base && (
              <span className="chip warn" title="你编辑的那版默认值已被升级改动">
                基线过时
              </span>
            )}
          </span>
        </button>
        {open && (
          <div className="prompt-body">
            <p className="hint">{it.note}</p>
            {!it.editable && (
              <p className="pane-hint warn">
                这是量具，只读。已记录的评测数字都是用这段字符串产出的；
                改动会让新旧结果不可比，且无从察觉。
              </p>
            )}
            {it.required.length > 0 && (
              <p className="hint">
                必须保留占位符：
                {it.required.map((t) => (
                  <code key={t} className="chip">
                    {t}
                  </code>
                ))}
              </p>
            )}
            <textarea
              className="prompt-text"
              value={body}
              readOnly={!it.editable}
              spellCheck={false}
              rows={Math.min(24, Math.max(6, body.split("\n").length + 2))}
              onChange={(e) =>
                setDrafts((d) => ({ ...d, [it.key]: e.target.value }))
              }
            />
            {it.editable && (
              <div className="prompt-actions">
                <button
                  className="btn primary"
                  disabled={busy || !dirty(it)}
                  onClick={() => save(it)}
                >
                  {dirty(it) ? "保存" : "无改动"}
                </button>
                <button
                  className="btn ghost"
                  disabled={busy || (!it.overridden && !dirty(it))}
                  onClick={() => reset(it)}
                >
                  恢复默认
                </button>
                <span className="spacer" />
                <span className="hint">
                  {body.length} 字符
                  {it.overridden &&
                    `　·　与默认相差 ${it.diff.chars > 0 ? "+" : ""}${it.diff.chars}`}
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="pane prompts-pane">
      <div className="pane-title">
        调校
        <span className="spacer" />
        <button className="btn ghost" onClick={onClose}>
          返回
        </button>
      </div>
      <p className="pane-hint">
        工具发出的每一条指令都在这里。改动立即对所有项目生效，
        与哪一本书无关。当前改过 {nOverridden} / {editable.length} 条。
      </p>
      {err && <p className="error">{err}</p>}

      <div className="prompt-group-label">创作类 · 可编辑</div>
      {editable.map(row)}

      <div className="prompt-group-label">量具 · 只读</div>
      <p className="hint">
        这三条决定了项目里所有数字的含义，所以不给改——但也不藏起来。
      </p>
      {locked.map(row)}
    </div>
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

/* ---------- 架构 · 线索 ---------- */
// 伏笔和认知状态原本是两个页签，但它们说的是同一件事：一条伏笔就是一条被隐瞒的
// 事实。分开登记意味着同一个故事元素要录两遍，而且两边容易对不上。
// 这里一张卡管到底：埋了没收 + 谁知道什么 + 什么时候放出来。

const LEVELS = [
  ["unknown", "不知道"],
  ["suspects", "怀疑"],
  ["knows", "知道"],
  ["believes_false", "误信"],
];

function CluesPane({ projectId, chapter, chapters = [] }) {
  const [threads, setThreads] = useState(null);
  const [facts, setFacts] = useState([]);
  const [characters, setCharacters] = useState([]);
  const [events, setEvents] = useState([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState(null);

  const reload = async () => {
    try {
      const [t, f, c, e] = await Promise.all([
        api.listForeshadowing(projectId),
        api.listFacts(projectId),
        api.listCharacters(projectId),
        api.listEvents(projectId),
      ]);
      setThreads(t);
      setFacts(f);
      setCharacters(c);
      setEvents(e);
    } catch (err) {
      setError(err.message);
    }
  };
  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // A clue is a fact first: the awareness levels are what actually drive the
  // constraints. Whether it is also a tracked thread (setup/payoff) is an extra
  // the author turns on — not every fact is a thread.
  const add = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setError(null);
    try {
      await api.createFact(projectId, { statement: title.trim() });
      setTitle("");
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };

  const patchFact = async (fact, body) => {
    try {
      await api.updateFact(projectId, fact.id, body);
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };

  // absent from the map = not modelled, which stays silent rather than
  // generating a constraint for every character in the book
  const setCharLevel = (fact, charId, level) => {
    const next = { ...fact.character_levels };
    if (level) next[charId] = level;
    else delete next[charId];
    patchFact(fact, { character_levels: next });
  };

  const markAsThread = async (fact) => {
    try {
      const t = await api.createForeshadowing(projectId, {
        title: fact.statement,
        setup_chapter_id: chapter?.id ?? null,
      });
      await api.updateFact(projectId, fact.id, { foreshadowing_id: t.id });
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleThread = async (t) => {
    await api.updateForeshadowing(
      projectId,
      t.id,
      t.status === "open"
        ? { status: "closed", payoff_chapter_id: chapter?.id ?? null }
        : { status: "open", payoff_chapter_id: null }
    );
    await reload();
  };

  const threadOf = (fact) =>
    threads?.find((t) => t.id === fact.foreshadowing_id) || null;
  // threads created before this merge have no fact attached yet
  const orphanThreads = (threads || []).filter(
    (t) => !facts.some((f) => f.foreshadowing_id === t.id)
  );

  const chapterName = (id) =>
    chapters.find((c) => c.id === id)?.title || (id ? `章节#${id}` : null);

  return (
    <div className="pane">
      <p className="pane-hint">
        一条线索 = <strong>埋了没收</strong> + <strong>谁知道什么</strong>。
        写场景计划时会自动编译成「不能发生」的约束：没登记的角色不产生约束。
      </p>
      <form className="thread-form" onSubmit={add}>
        <input
          value={title}
          placeholder="一句话陈述，如：晴湾是被装着的"
          onChange={(e) => setTitle(e.target.value)}
        />
        <button className="btn primary" type="submit">
          登记线索
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {facts.length === 0 && orphanThreads.length === 0 && (
        <p className="empty">
          还没有线索。
          <br />
          登记几条之后，生成场景计划时会自动带上连续性约束。
        </p>
      )}

      {facts.map((f) => {
        const t = threadOf(f);
        return (
          <div className="slip fact" key={f.id} style={{ "--slip-heat": 0.6 }}>
            <div className="slip-head">
              <span className="slip-tag">
                {t ? (t.status === "open" ? "伏笔·未收" : "伏笔·已收") : "事实"}
                {f.is_true ? "" : " · 不实"}
              </span>
              <span className="thread-actions">
                {t ? (
                  <button onClick={() => toggleThread(t)}>
                    {t.status === "open" ? "标为已回收" : "重新打开"}
                  </button>
                ) : (
                  <button onClick={() => markAsThread(f)}>标为伏笔</button>
                )}
                <button onClick={() => patchFact(f, { is_true: !f.is_true })}>
                  {f.is_true ? "标为不实" : "标为属实"}
                </button>
                <button onClick={() => api.deleteFact(projectId, f.id).then(reload)}>
                  删除
                </button>
              </span>
            </div>
            <p className="slip-body">
              <strong>{f.statement}</strong>
            </p>
            {t && (
              <p className="cite">
                埋设：{chapterName(t.setup_chapter_id) || "未记录"}
                {t.payoff_chapter_id
                  ? ` · 回收：${chapterName(t.payoff_chapter_id)}`
                  : ""}
              </p>
            )}
            <label className="fact-row">
              <span>读者</span>
              <select
                value={f.reader_level}
                onChange={(e) => patchFact(f, { reader_level: e.target.value })}
              >
                {LEVELS.map(([v, label]) => (
                  <option key={v} value={v}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {characters.map((c) => (
              <label className="fact-row" key={c.id}>
                <span>{c.name}</span>
                <select
                  value={f.character_levels?.[String(c.id)] || ""}
                  onChange={(e) => setCharLevel(f, c.id, e.target.value)}
                >
                  <option value="">未登记</option>
                  {LEVELS.map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <FactTimeline
              projectId={projectId}
              fact={f}
              chapters={chapters}
              characters={characters}
              events={events.filter((e) => e.fact_id === f.id)}
              onChange={reload}
            />
          </div>
        );
      })}

      {orphanThreads.length > 0 && (
        <>
          <p className="pane-hint" style={{ marginTop: 14 }}>
            以下伏笔还没登记认知状态，补上之后才会参与约束推导：
          </p>
          {orphanThreads.map((t) => (
            <div className="slip" key={t.id} style={{ "--slip-heat": 0.3 }}>
              <div className="slip-head">
                <span className="slip-tag">
                  {t.status === "open" ? "伏笔·未收" : "伏笔·已收"}
                </span>
                <span className="thread-actions">
                  <button
                    onClick={async () => {
                      const f = await api.createFact(projectId, {
                        statement: t.title,
                        foreshadowing_id: t.id,
                      });
                      if (f) await reload();
                    }}
                  >
                    补登记认知
                  </button>
                  <button onClick={() => toggleThread(t)}>
                    {t.status === "open" ? "标为已回收" : "重新打开"}
                  </button>
                  <button
                    onClick={() =>
                      api.deleteForeshadowing(projectId, t.id).then(reload)
                    }
                  >
                    删除
                  </button>
                </span>
              </div>
              <p className="slip-body">
                <strong>{t.title}</strong>
              </p>
              {t.content && <p className="cite">{t.content}</p>}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// The information-release schedule for one clue: who reaches which level, and
// from which chapter. The levels above are the opening state; each entry here
// overrides it from its chapter onward, so a scene planned for chapter three
// gets chapter three's prohibitions rather than today's.
function FactTimeline({ projectId, fact, chapters, characters, events, onChange }) {
  const [open, setOpen] = useState(false);
  const [holder, setHolder] = useState("reader");
  const [level, setLevel] = useState("knows");
  const [chapterId, setChapterId] = useState("");
  const [busy, setBusy] = useState(false);

  const nameOf = (e) =>
    e.holder_type === "reader"
      ? "读者"
      : characters.find((c) => c.id === e.holder_id)?.name || `角色${e.holder_id}`;
  const chapterOf = (id) =>
    chapters.find((c) => c.id === id)?.title || (id ? `章节#${id}` : "开篇起");

  const add = async () => {
    setBusy(true);
    try {
      await api.createEvent(projectId, {
        fact_id: fact.id,
        holder_type: holder === "reader" ? "reader" : "character",
        holder_id: holder === "reader" ? null : Number(holder),
        level,
        chapter_id: chapterId ? Number(chapterId) : null,
      });
      await onChange();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fact-timeline">
      <button className="timeline-toggle" onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"} 释放时机{events.length > 0 && ` · ${events.length} 条`}
      </button>
      {open && (
        <>
          {events.length === 0 && (
            <p className="pane-hint">
              未登记时机时，上面的档位一直有效。登记之后，约束会随章节推进自动变化。
            </p>
          )}
          {events.map((e) => (
            <div className="timeline-row" key={e.id}>
              <span>
                {nameOf(e)} 从《{chapterOf(e.chapter_id)}》起 →{" "}
                <strong>{LEVELS.find(([v]) => v === e.level)?.[1] || e.level}</strong>
              </span>
              <button onClick={() => api.deleteEvent(projectId, e.id).then(onChange)}>
                删除
              </button>
            </div>
          ))}
          <div className="timeline-add">
            <select value={holder} onChange={(ev) => setHolder(ev.target.value)}>
              <option value="reader">读者</option>
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select value={chapterId} onChange={(ev) => setChapterId(ev.target.value)}>
              <option value="">开篇起</option>
              {chapters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || `第${c.order_index}章`}
                </option>
              ))}
            </select>
            <select value={level} onChange={(ev) => setLevel(ev.target.value)}>
              {LEVELS.map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
            <button className="btn ghost" onClick={add} disabled={busy}>
              添加
            </button>
          </div>
        </>
      )}
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
    // 并入即场景边界，记一个场景单元
    api
      .createUnit(projectId, { chapter_id: chapter?.id, text: draft })
      .catch(() => {});
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

// A locked field survives regeneration untouched. Shown inline with the field
// it protects so the decision and its lock are never separated.
function LockToggle({ field, locked, onToggle }) {
  const on = locked.includes(field);
  return (
    <button
      type="button"
      className={`lock-toggle${on ? " on" : ""}`}
      title={on ? "已锁定：重新生成不会覆盖" : "锁定后，重新生成不会覆盖这一项"}
      aria-pressed={on}
      onClick={(e) => {
        e.preventDefault();
        onToggle(field);
      }}
    >
      {on ? "🔒" : "🔓"}
    </button>
  );
}

// Compile a candidate or a plan into the free-text directive that 续写 and 仿写
// take. This is what the old 细纲 tab existed for — a light exit that skips the
// verified write loop when the author would rather steer and type it themselves.
function candidateToDirective(c) {
  return [
    `走向：${c.summary}`,
    c.conflict_source && `冲突来源：${c.conflict_source}`,
    c.agency && `主动/被动：${c.agency}`,
    c.reveal_order && `信息揭示顺序：${c.reveal_order}`,
    c.emotion_arc && `情绪走势：${c.emotion_arc}`,
    c.turn && `转折机制：${c.turn}`,
    c.open_question && `结尾悬念：${c.open_question}`,
  ]
    .filter(Boolean)
    .join("\n");
}

function planToDirective(p) {
  return [
    p.goal && `本场目标：${p.goal}`,
    p.desire && `角色欲望：${p.desire}`,
    p.conflict && `冲突：${p.conflict}`,
    p.info_shift && `信息变化：${p.info_shift}`,
    p.emotion_curve && `情绪曲线：${p.emotion_curve}`,
    p.must_include?.length && `必须出现：${p.must_include.join("；")}`,
    [...(p.must_not || []), ...(p.derived_must_not || [])].length &&
      `不能发生：${[...(p.must_not || []), ...(p.derived_must_not || [])].join("；")}`,
    p.end_state && `结尾状态：${p.end_state}`,
  ]
    .filter(Boolean)
    .join("\n");
}

function RefinePane({ projectId, chapter, onAppend, onContinue, onImitate }) {
  const [fragment, setFragment] = useState("");
  const [candidates, setCandidates] = useState(null); // ① options
  const [picked, setPicked] = useState({}); // index -> bool (merge set)
  const [plan, setPlan] = useState(null); // ② editable ScenePlan
  const [planId, setPlanId] = useState(null); // saved plan row — locks live here
  const [locked, setLocked] = useState([]); // ScenePlan fields frozen by the author
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
      // passing the previous plan id carries locked fields forward untouched
      const resp = await api.refinePlan(
        projectId,
        fragment.trim(),
        candidate,
        chapter?.id ?? null,
        planId
      );
      setPlan(resp.plan);
      setPlanId(resp.plan_id ?? null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // Locks live on the saved plan row, not in local state — a lock the server
  // never heard about would be silently ignored by the next regeneration.
  const toggleLock = async (field) => {
    const next = locked.includes(field)
      ? locked.filter((f) => f !== field)
      : [...locked, field];
    setLocked(next);
    if (!planId) return;
    try {
      await api.updatePlan(projectId, planId, { plan, locked_fields: next });
    } catch (err) {
      setLocked(locked); // put the UI back where the server actually is
      setError(`锁定失败：${err.message}`);
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
    // 并入即场景边界；带 plan_id 时把计划与成稿关联并推进为 accepted，
    // 「计划了什么 vs 实际写了什么」从此是个有答案的问题
    api
      .createUnit(projectId, {
        chapter_id: chapter?.id,
        text: draft,
        plan_id: planId,
      })
      .catch(() => {});
    setResult(null);
    setDraft("");
    setPlan(null);
    setPlanId(null);
    setLocked([]);
    setCandidates(null);
  };

  return (
    <div className="pane">
      <p className="pane-hint">
        <strong>精修</strong>：多候选走向 → 选 / 合并 → 场景计划（必须出现 / 不能发生）
        → 依计划生成 → <strong>逐条核对约束</strong>，不达标自动重写。最慢也最稳，出精稿。
        <br />
        任何一步都能<strong>中途退出</strong>——把候选或计划直接交给续写/仿写，自己动手写。
      </p>

      {/* ① 片段输入 */}
      {!candidates && !plan && !result && (
        <>
          <textarea
            className="ingest-text"
            rows={4}
            value={fragment}
            placeholder="粘贴当前写到的正文片段；卡住写不下去时，直接描述你卡在哪也行"
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
            {/* light exit: take the direction and write it yourself */}
            <button
              className="btn ghost"
              onClick={() => {
                const c = mergeSelected();
                if (!c) return setError("先勾选至少一条候选。");
                onContinue?.(candidateToDirective(c));
                setNote("已填入稿纸的方向指引——回到稿纸点『往下写』。");
              }}
            >
              → 续写
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
              <span>
                {label}
                <LockToggle field={k} locked={locked} onToggle={toggleLock} />
              </span>
              <textarea
                rows={1}
                value={plan[k] || ""}
                onChange={(e) => setField(k, e.target.value)}
              />
            </label>
          ))}
          <label className="refine-field">
            <span>
              必须出现（每行一条，会逐条核对）
              <LockToggle field="must_include" locked={locked} onToggle={toggleLock} />
            </span>
            <textarea
              rows={3}
              value={(plan.must_include || []).join("\n")}
              onChange={(e) => setList("must_include", e.target.value)}
            />
          </label>
          <label className="refine-field">
            <span>
              不能发生（每行一条，会逐条核对）
              <LockToggle field="must_not" locked={locked} onToggle={toggleLock} />
            </span>
            <textarea
              rows={2}
              value={(plan.must_not || []).join("\n")}
              onChange={(e) => setList("must_not", e.target.value)}
            />
          </label>
          {/* read-only: compiled from the knowledge table, not written by the
              planner — shown separately so editing the plan can't drop them */}
          {plan.derived_must_not?.length > 0 && (
            <div className="refine-field">
              <span>由知识状态自动推导（同样会逐条核对）</span>
              <ul className="derived-list">
                {plan.derived_must_not.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="ingest-actions">
            <button className="btn ghost" onClick={() => setPlan(null)} disabled={busy}>
              ← 重选候选
            </button>
            {/* light exits: hand the plan to 续写 or 仿写 instead of the
                verified write loop — cheaper, and the author keeps the pen */}
            <button
              className="btn ghost"
              onClick={() => {
                onContinue?.(planToDirective(plan));
                setNote("已填入稿纸的方向指引——回到稿纸点『往下写』。");
              }}
            >
              → 续写
            </button>
            <button
              className="btn ghost"
              onClick={() => onImitate?.(planToDirective(plan))}
            >
              → 仿写
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
                        {k.source === "knowledge" && (
                          <span className="derived-mark">知识</span>
                        )}
                        {k.source === "program" && (
                          <span className="derived-mark">程序</span>
                        )}
                        {k.evidence && k.source === "program" && !k.satisfied && (
                          <span className="check-evidence">{k.evidence}</span>
                        )}
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
