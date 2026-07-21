# -*- coding: utf-8 -*-
"""Import an epub's prose into a project's PRIVATE style library.

The style library is user-private data for personal writing assistance.
Nothing this script touches may enter the repo: epubs and any derived
exports are gitignored, chunks live only in the local database, and the
generation prompt explicitly forbids reproducing sample content (backed by
an n-gram overlap check in the imitation self-check loop).

    python scripts/import_style_epub.py --source path/to/book.epub \
        --project-id 5 [--max-chunks 1200]

Chunking: paragraphs are merged into ~CHUNK_TARGET-char scene-sized blocks;
front/back matter and too-short documents are skipped heuristically.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import time
import zipfile
from html.parser import HTMLParser

from sqlalchemy import select

from app.core.embedding import embed_texts
from app.db import AsyncSessionLocal
from app.models.setting_chunk import SettingChunk

CHUNK_TARGET = 400   # chars per style sample — one beat of a scene
CHUNK_MIN = 150      # drop trailing fragments shorter than this
DOC_MIN = 500        # skip docs shorter than this (TOC, copyright, images)
BATCH = 64


class _TextExtractor(HTMLParser):
    """Pull visible text out of an xhtml chapter, paragraph-aware."""

    _SKIP = {"script", "style", "head", "title"}
    _BREAKERS = {"p", "div", "br", "h1", "h2", "h3", "li"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAKERS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BREAKERS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t　]+", " ", ln).strip() for ln in raw.split("\n")]
        return "\n".join(ln for ln in lines if ln)


def extract_docs(epub_path: str) -> list[str]:
    docs: list[str] = []
    with zipfile.ZipFile(epub_path) as z:
        names = sorted(
            n for n in z.namelist() if n.endswith((".html", ".xhtml", ".htm"))
        )
        for name in names:
            payload = z.read(name)
            for enc in ("utf-8", "gb18030"):
                try:
                    html = payload.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                continue
            parser = _TextExtractor()
            parser.feed(html)
            text = parser.text()
            if len(text) >= DOC_MIN:
                docs.append(text)
    return docs


def chunk_doc(text: str) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in text.split("\n"):
        buf.append(para)
        size += len(para)
        if size >= CHUNK_TARGET:
            chunks.append("\n".join(buf))
            buf, size = [], 0
    if buf and size >= CHUNK_MIN:
        chunks.append("\n".join(buf))
    return chunks


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--max-chunks", type=int, default=1200,
                    help="evenly sampled cap so import time stays sane")
    args = ap.parse_args()

    docs = extract_docs(args.source)
    chunks = [c for d in docs for c in chunk_doc(d)]
    print(f"docs kept: {len(docs)}, chunks cut: {len(chunks)}")

    if len(chunks) > args.max_chunks:
        step = len(chunks) / args.max_chunks
        chunks = [chunks[int(i * step)] for i in range(args.max_chunks)]
        print(f"evenly sampled down to {len(chunks)}")

    async with AsyncSessionLocal() as db:
        existing = set(
            (
                await db.execute(
                    select(SettingChunk.content).where(
                        SettingChunk.project_id == args.project_id,
                        SettingChunk.source_type == "style",
                    )
                )
            ).scalars().all()
        )
        new = [c for c in chunks if c not in existing]
        print(f"new chunks to embed: {len(new)} (skipped {len(chunks) - len(new)} dup)")

        t0 = time.perf_counter()
        for i in range(0, len(new), BATCH):
            batch = new[i : i + BATCH]
            vectors = await embed_texts(batch)
            for content, vec in zip(batch, vectors):
                db.add(
                    SettingChunk(
                        project_id=args.project_id,
                        source_type="style",
                        source_id=None,
                        source_label="epub",
                        content=content,
                        embedding=vec,
                    )
                )
            await db.commit()
            done = min(i + BATCH, len(new))
            rate = done / (time.perf_counter() - t0)
            print(f"  {done}/{len(new)}  ({rate:.0f} chunks/s)", flush=True)
    print("style import complete.")


if __name__ == "__main__":
    asyncio.run(main())
