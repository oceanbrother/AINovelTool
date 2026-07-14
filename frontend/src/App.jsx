import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, streamContinue } from "./api.js";
import MusePanel from "./MusePanel.jsx";

export default function App() {
  const [projects, setProjects] = useState(null);
  const [projectId, setProjectId] = useState(null);

  useEffect(() => {
    api.listProjects().then((rows) => {
      setProjects(rows);
      if (rows.length > 0) setProjectId(rows[0].id);
    });
  }, []);

  const createProject = async (title) => {
    const p = await api.createProject({ title, genre: "都市幻想" });
    setProjects([...(projects || []), p]);
    setProjectId(p.id);
  };

  if (projects === null) return null;
  if (projects.length === 0) return <Gate onCreate={createProject} />;

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark">
          夜写台<span className="seal">·</span>
        </span>
        <select
          value={projectId ?? ""}
          onChange={(e) => setProjectId(Number(e.target.value))}
          aria-label="切换作品"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
        <span className="spacer" />
        <span className="hint">设定在库，检索为据，笔在你手</span>
      </header>
      {projectId != null && <Workspace key={projectId} projectId={projectId} />}
    </div>
  );
}

function Gate({ onCreate }) {
  const [title, setTitle] = useState("");
  return (
    <div className="gate">
      <h1>
        夜写台<span className="seal">·</span>
      </h1>
      <p>还没有作品。起一个书名，开始你的第一章。</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim()) onCreate(title.trim());
        }}
      >
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="书名，如：龙城暗涌"
          autoFocus
        />
        <button className="btn primary" type="submit">
          开新书
        </button>
      </form>
    </div>
  );
}

function Workspace({ projectId }) {
  const [chapters, setChapters] = useState([]);
  const [chapterId, setChapterId] = useState(null);
  const chapter = chapters.find((c) => c.id === chapterId) || null;

  useEffect(() => {
    api.listChapters(projectId).then((rows) => {
      rows.sort((a, b) => a.order_index - b.order_index || a.id - b.id);
      setChapters(rows);
      if (rows.length > 0) setChapterId(rows[0].id);
    });
  }, [projectId]);

  const addChapter = async () => {
    const order = chapters.length + 1;
    const ch = await api.createChapter(projectId, {
      title: `第${order}章`,
      order_index: order,
    });
    setChapters([...chapters, ch]);
    setChapterId(ch.id);
  };

  const patchChapter = (cid, patch) =>
    setChapters((chs) => chs.map((c) => (c.id === cid ? { ...c, ...patch } : c)));

  return (
    <div className="workspace">
      <nav className="rail">
        <div className="rail-head">
          <h2>章节</h2>
          <button onClick={addChapter}>＋新章</button>
        </div>
        {chapters.length === 0 ? (
          <p className="empty">还没有章节。点「＋新章」落笔。</p>
        ) : (
          <ul>
            {chapters.map((c, i) => (
              <li key={c.id}>
                <button
                  className={`chapter-item${c.id === chapterId ? " active" : ""}`}
                  onClick={() => setChapterId(c.id)}
                >
                  <span className="no">{String(i + 1).padStart(2, "0")}</span>
                  {c.title || "未命名"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>

      {chapter ? (
        <Editor
          key={chapter.id}
          projectId={projectId}
          chapter={chapter}
          onLocalChange={patchChapter}
        />
      ) : (
        <div className="desk">
          <div className="paper">
            <p style={{ padding: "56px", color: "#b0ab9b", fontFamily: "var(--serif)" }}>
              选择或新建一个章节。
            </p>
          </div>
          <div className="deskbar" />
        </div>
      )}

      <MusePanel projectId={projectId} chapter={chapter} />
    </div>
  );
}

function Editor({ projectId, chapter, onLocalChange }) {
  const [title, setTitle] = useState(chapter.title || "");
  const [content, setContent] = useState(chapter.content || "");
  const [saveState, setSaveState] = useState("已保存");
  const [instruction, setInstruction] = useState("");
  const [streamText, setStreamText] = useState(null); // null = not streaming
  const [busy, setBusy] = useState(false);
  const abortRef = useRef(null);
  const saveTimer = useRef(null);
  const streamRef = useRef(null);

  // debounced autosave
  const scheduleSave = useCallback(
    (nextTitle, nextContent) => {
      setSaveState("未保存");
      clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        setSaveState("保存中…");
        await api.updateChapter(projectId, chapter.id, {
          title: nextTitle,
          content: nextContent,
        });
        onLocalChange(chapter.id, { title: nextTitle, content: nextContent });
        setSaveState("已保存");
      }, 800);
    },
    [projectId, chapter.id, onLocalChange]
  );

  useEffect(() => () => clearTimeout(saveTimer.current), []);

  useEffect(() => {
    if (streamRef.current)
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [streamText]);

  const startContinue = async () => {
    setBusy(true);
    setStreamText("");
    abortRef.current = new AbortController();
    let acc = "";
    try {
      await streamContinue(
        projectId,
        chapter.id,
        instruction,
        (tok) => {
          acc += tok;
          setStreamText(acc);
        },
        abortRef.current.signal
      );
    } catch (err) {
      if (err.name !== "AbortError") {
        setStreamText((t) => `${t || ""}\n〔生成中断：${err.message}〕`);
      }
    } finally {
      setBusy(false);
    }
  };

  const acceptStream = () => {
    const merged = content ? `${content}\n${streamText}` : streamText;
    setContent(merged);
    setStreamText(null);
    scheduleSave(title, merged);
  };

  const discardStream = () => {
    abortRef.current?.abort();
    setStreamText(null);
  };

  return (
    <div className="desk">
      <div className="paper">
        <div className="title-row">
          <input
            value={title}
            placeholder="章节标题"
            onChange={(e) => {
              setTitle(e.target.value);
              scheduleSave(e.target.value, content);
            }}
          />
        </div>
        <textarea
          className="prose"
          value={content}
          placeholder="从这里开始写。写不下去的时候，交给下面的「往下写」或「破壁」。"
          onChange={(e) => {
            setContent(e.target.value);
            scheduleSave(title, e.target.value);
          }}
        />
        {streamText !== null && (
          <div className="streaming" ref={streamRef} aria-live="polite">
            {streamText}
            {busy && <span className="cursor" />}
          </div>
        )}
      </div>

      <div className="deskbar">
        <span className="savestate">{saveState}</span>
        <input
          type="text"
          value={instruction}
          placeholder="可选的方向指引，如：让主角识破伪装"
          onChange={(e) => setInstruction(e.target.value)}
        />
        {streamText === null ? (
          <button className="btn primary" onClick={startContinue} disabled={busy}>
            往下写
          </button>
        ) : busy ? (
          <button className="btn ghost" onClick={discardStream}>
            停下
          </button>
        ) : (
          <>
            <button className="btn primary" onClick={acceptStream}>
              并入正文
            </button>
            <button className="btn ghost" onClick={discardStream}>
              弃稿
            </button>
          </>
        )}
      </div>
    </div>
  );
}
