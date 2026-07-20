// Thin client over the FastAPI backend (proxied by vite dev server).

async function json(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${text.slice(0, 200)}`);
  }
  return resp.status === 204 ? null : resp.json();
}

export const api = {
  listProjects: () => json("GET", "/projects"),
  createProject: (payload) => json("POST", "/projects", payload),

  listChapters: (pid) => json("GET", `/projects/${pid}/chapters`),
  createChapter: (pid, payload) => json("POST", `/projects/${pid}/chapters`, payload),
  updateChapter: (pid, cid, payload) =>
    json("PATCH", `/projects/${pid}/chapters/${cid}`, payload),

  listCharacters: (pid) => json("GET", `/projects/${pid}/characters`),
  createCharacter: (pid, payload) =>
    json("POST", `/projects/${pid}/characters`, payload),
  listWorld: (pid) => json("GET", `/projects/${pid}/world`),
  createWorld: (pid, payload) => json("POST", `/projects/${pid}/world`, payload),

  listForeshadowing: (pid) => json("GET", `/projects/${pid}/foreshadowing`),
  createForeshadowing: (pid, payload) =>
    json("POST", `/projects/${pid}/foreshadowing`, payload),
  updateForeshadowing: (pid, fid, payload) =>
    json("PATCH", `/projects/${pid}/foreshadowing/${fid}`, payload),
  deleteForeshadowing: (pid, fid) =>
    json("DELETE", `/projects/${pid}/foreshadowing/${fid}`),

  retrieve: (pid, query, topK = 5) =>
    json("POST", `/projects/${pid}/retrieve`, { query, top_k: topK }),

  breakthrough: (pid, chapterId, state, n = 3) =>
    json("POST", `/projects/${pid}/generate/breakthrough`, {
      chapter_id: chapterId,
      state,
      num_branches: n,
    }),

  suggestIdioms: (scene) => json("POST", "/idioms/suggest", { scene }),
  literaryQuotes: (query, category, library) =>
    json("POST", "/literary/quotes", {
      query,
      category: category || null,
      library: library || null,
    }),
};

// POST-based SSE: EventSource only supports GET, so parse the stream manually.
// Calls onClues(chunks) once retrieval lands (before the first LLM token) and
// onToken(text) per token; resolves when the server sends `done`.
export async function streamContinue(pid, chapterId, instruction, onToken, signal, onClues) {
  const resp = await fetch(`/projects/${pid}/generate/continue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chapter_id: chapterId, instruction: instruction || null }),
    signal,
  });
  if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).replace(/\r$/, "");
      buffer = buffer.slice(idx + 1);
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const data = line.slice(5).replace(/^ /, "");
        if (event === "token") onToken(data);
        else if (event === "clues" && onClues) onClues(JSON.parse(data));
        else if (event === "error") throw new Error(data);
        else if (event === "done") return;
      }
    }
  }
}
