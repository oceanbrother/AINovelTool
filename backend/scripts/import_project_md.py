# -*- coding: utf-8 -*-
"""Import a folder of markdown setting docs into a new project.

A general-purpose importer for the common case where a writer keeps their
worldbuilding as a folder of .md files. Convention (deliberately simple so it
works on any such folder):

  * one project is created for the whole folder
  * each .md file becomes a world-setting *category* (category = filename stem)
  * each level-2 heading (`## …`) inside a file becomes one entry
    (title = heading, content = the text under it until the next `##`)
  * a file with no `##` becomes a single entry titled after the filename

Everything lands in world_settings, which is retrievable regardless of kind —
a generic tool can't reliably tell a character card from a location, so it
uses one uniform sink rather than guessing. Curate into characters/foreshadowing
afterward in the app if you want finer structure.

Entries go through the running API, so each is embedded and indexed exactly
like an in-app write.

    python scripts/import_project_md.py --dir path/to/notes --title "书名" \
        [--genre 都市幻想] [--base-url http://localhost:8000]

NOTE: this ships the *parser*, never anyone's content — point it at your own
folder. Private material must not be committed to the repo.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import httpx


def parse_file(text: str, stem: str) -> list[tuple[str, str]]:
    """Split a markdown doc into (title, content) entries by level-2 headings.

    Level-1 (`# …`) lines are dropped — they're the doc title, not an entry.
    Text before the first `##` is dropped as preamble WHEN the file has `##`
    sections; a file with no `##` at all becomes one entry titled after the
    filename.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    entries: list[tuple[str, str]] = []
    cur_title: str | None = None
    buf: list[str] = []

    def flush():
        if cur_title is None:  # preamble before the first ## — discard
            return
        body = "\n".join(buf).strip()
        if body:
            entries.append((cur_title, body))

    for line in lines:
        if re.match(r"^#\s+", line):  # H1 title line — skip
            continue
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            flush()
            cur_title = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    flush()

    if not entries:  # no ## headings anywhere → whole file is one entry
        body = "\n".join(buf).strip()
        if body:
            entries.append((stem, body))
    return entries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="folder of .md setting docs")
    ap.add_argument("--title", required=True)
    ap.add_argument("--genre", default="都市幻想")
    ap.add_argument("--base-url", default="http://localhost:8000")
    args = ap.parse_args()

    folder = Path(args.dir)
    md_files = sorted(folder.glob("*.md"))
    if not md_files:
        raise SystemExit(f"no .md files in {folder}")

    with httpx.Client(base_url=args.base_url, timeout=120) as c:
        proj = c.post(
            "/projects",
            json={"title": args.title, "genre": args.genre,
                  "description": f"从 {folder.name}/ 导入"},
        ).json()
        pid = proj["id"]
        print(f"project {pid}: {args.title}")

        total = 0
        for f in md_files:
            stem = f.stem
            entries = parse_file(f.read_text(encoding="utf-8"), stem)
            for title, content in entries:
                c.post(
                    f"/projects/{pid}/world",
                    json={"category": stem, "title": title, "content": content},
                ).raise_for_status()
            total += len(entries)
            print(f"  {f.name}: {len(entries)} entries")
        print(f"done. {total} world-setting entries into project {pid}.")


if __name__ == "__main__":
    main()
