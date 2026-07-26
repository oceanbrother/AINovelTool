# -*- coding: utf-8 -*-
"""Ingest a reference book into `corpus_segments` — ORDERED, for rhythm analysis.

Why not reuse import_style_epub.py: that script serves *retrieval*. It cuts at
fixed 400-char boundaries, evenly samples the book down to N chunks
(`chunks[int(i*step)]`) and dedupes — all of which destroy adjacency, the one
property rhythm modelling needs. Here nothing is sampled away and every segment
keeps (chapter_no, seq).

Two correctness fixes over the older importer:
  * chapter order comes from the epub SPINE, not `sorted(namelist())`. Filename
    order matches spine only when filenames happen to be zero-padded; relying on
    that is luck, not correctness.
  * segments are cut at scene switches (transition markers / length envelope),
    not at a fixed character count.

    python scripts/build_corpus.py --source path/to/book.epub --work 龙族
    python scripts/build_corpus.py --source book.txt --work X --replace

Corpus prose is local-only private data (.gitignore: *.epub, style_data/).
Only aggregate statistics derived from it may ever leave this machine.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import statistics
import time
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

from sqlalchemy import delete, select

from app.core.embedding import embed_texts
from app.db import AsyncSessionLocal
from app.models.corpus_segment import CorpusSegment
from app.services import rhythm

DOC_MIN = 3000        # skip front/back matter, part dividers, TOC
SEG_MIN = 200         # never emit a segment shorter than this (merge back)
SEG_MAX = 1200        # hard cap so a valley-free stretch still gets cut

# Semantic segmentation (TextTiling-style). Measured against the marker-only
# heuristic on this corpus: markers open just 0.2% of paragraphs and drove only
# 2.3% of cuts, i.e. marker segmentation silently degenerates into fixed-length
# chunking (length sd 81 vs 211, median pinned near the cap). Embedding valleys
# drive 99-100% of cuts instead, so segments track scene changes, not a counter.
TILE_WINDOW = 3       # paragraphs averaged on each side of a candidate gap
TILE_PEAK_SPAN = 5    # neighbourhood used to find the peaks around a valley
TILE_Z = 0.5          # a valley must sit this many sd below the chapter's mean

# Chapter heading: a short leading paragraph like 第一幕 / 第三章 / 序 / 尾声.
_TITLE_RE = re.compile(r"^(第[〇零一二三四五六七八九十百千\d]+[幕章节回]|序[章幕]?|楔子|尾声|后记)")

# Strong scene-switch openers only. Deliberately excludes high-frequency
# intra-scene connectives (这时/随后/片刻后...) — using those over-segments
# badly in dialogue-dense prose, where they appear constantly.
_SWITCH_RE = re.compile(
    r"^("
    r"第二天|第三天|次日|翌日|当天|当晚|当夜|那天|那晚|那一夜|"
    r"傍晚|清晨|凌晨|深夜|入夜|天亮|天黑|黎明|午后|黄昏|"
    r"[一两二三四五六七八九十百\d]+(分钟|小时|天|周|星期|个?月|年)(之?后|以后)|"
    r"几(分钟|小时|天|周|个月|年)(之?后|以后)|半(小时|个月|年)(之?后|以后)|"
    r"多年(以)?后|后来|从那(以后|天起)|从此|"
    r"与此同时|同一(时刻|时间)|另一(边|头|侧)|而在|远在"
    r")"
)


class _Paragraphs(HTMLParser):
    """Extract visible text as a list of paragraphs (block structure kept).

    Unlike the retrieval importer's extractor, which joins everything into one
    string, paragraph boundaries are preserved — segmentation needs them.
    """

    _SKIP = {"script", "style", "head", "title"}
    _BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "li", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._buf: list[str] = []
        self.paras: list[str] = []

    def _flush(self) -> None:
        s = re.sub(r"[ \t　]+", " ", "".join(self._buf)).strip()
        self._buf = []
        if s:
            self.paras.append(s)

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def read_epub_chapters(path: str) -> list[list[str]]:
    """Chapters as paragraph lists, in SPINE order (not filename order)."""
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = container.find(".//{*}rootfile").get("full-path")
        opf = ET.fromstring(z.read(opf_path))
        manifest = {it.get("id"): it.get("href") for it in opf.find("{*}manifest")}
        base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""

        chapters: list[list[str]] = []
        for itemref in opf.find("{*}spine"):
            href = manifest.get(itemref.get("idref"))
            if not href or not href.endswith((".html", ".xhtml", ".htm")):
                continue
            name = base + href
            if name not in z.namelist():
                name = href
                if name not in z.namelist():
                    continue
            parser = _Paragraphs()
            parser.feed(z.read(name).decode("utf-8", "ignore"))
            parser.close()
            if sum(len(p) for p in parser.paras) >= DOC_MIN:
                chapters.append(parser.paras)
    return chapters


def read_txt_chapters(path: str) -> list[list[str]]:
    """Plain text fallback: split on chapter headings, keep paragraph breaks."""
    for enc in ("utf-8", "gb18030"):
        try:
            raw = open(path, encoding=enc).read()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit("cannot decode source file")
    paras = [p.strip() for p in raw.split("\n") if p.strip()]
    chapters: list[list[str]] = []
    current: list[str] = []
    for p in paras:
        if _TITLE_RE.match(p) and len(p) <= 30 and current:
            if sum(len(x) for x in current) >= DOC_MIN:
                chapters.append(current)
            current = []
        current.append(p)
    if current and sum(len(x) for x in current) >= DOC_MIN:
        chapters.append(current)
    return chapters


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _unit_mean(vecs: list[list[float]]) -> list[float]:
    n = len(vecs)
    mean = [sum(v[i] for v in vecs) / n for i in range(len(vecs[0]))]
    norm = sum(x * x for x in mean) ** 0.5 or 1.0
    return [x / norm for x in mean]


def valley_gaps(vecs: list[list[float]]) -> set[int]:
    """Paragraph indices that open a new scene, by TextTiling depth score.

    Every gap is scored by how dissimilar the block of paragraphs before it is
    from the block after. A gap is a boundary when its *depth* — how far it sits
    below the peaks on either side — stands out from that chapter's own noise,
    which keeps the threshold adaptive instead of a magic global constant.
    """
    if len(vecs) < 2 * TILE_WINDOW + 1:
        return set()
    gaps = [
        (i, _cosine(_unit_mean(vecs[i - TILE_WINDOW:i]), _unit_mean(vecs[i:i + TILE_WINDOW])))
        for i in range(TILE_WINDOW, len(vecs) - TILE_WINDOW + 1)
    ]
    sims = [s for _, s in gaps]
    depths = []
    for k, (i, s) in enumerate(gaps):
        left_peak = max(sims[max(0, k - TILE_PEAK_SPAN):k + 1])
        right_peak = max(sims[k:k + TILE_PEAK_SPAN + 1])
        depths.append((i, (left_peak - s) + (right_peak - s)))
    values = [d for _, d in depths]
    cutoff = statistics.mean(values) + TILE_Z * (statistics.pstdev(values) or 1e-9)
    return {i for i, d in depths if d > cutoff}


def segment(paras: list[str], boundaries: set[int] | None = None) -> list[str]:
    """Cut a chapter into scene-sized segments.

    Boundaries come from semantic valleys when available; the switch-marker
    regex is kept as a cheap extra signal (it fires rarely but is precise when
    it does), and the length cap is the backstop. Trailing fragments merge back
    so nothing tiny escapes.
    """
    boundaries = boundaries or set()
    segs: list[str] = []
    buf: list[str] = []
    size = 0
    for i, p in enumerate(paras):
        opens_scene = i in boundaries or bool(_SWITCH_RE.match(p))
        if buf and ((opens_scene and size >= SEG_MIN) or size >= SEG_MAX):
            segs.append("\n".join(buf))
            buf, size = [], 0
        buf.append(p)
        size += len(p)
    if buf:
        if size >= SEG_MIN or not segs:
            segs.append("\n".join(buf))
        else:  # too small to stand alone — fold into the previous segment
            segs[-1] += "\n" + "\n".join(buf)
    return segs


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--work", required=True, help="corpus label, e.g. 龙族")
    ap.add_argument("--replace", action="store_true", help="wipe this work first")
    ap.add_argument("--max-chapters", type=int, default=0, help="0 = all")
    ap.add_argument("--dry-run", action="store_true",
                    help="segment and report, write nothing — check the cuts first")
    ap.add_argument("--no-semantic", action="store_true",
                    help="skip embedding valleys (fast, but degenerates to length chunking)")
    args = ap.parse_args()

    reader = read_epub_chapters if args.source.lower().endswith(".epub") else read_txt_chapters
    chapters = reader(args.source)
    if args.max_chapters:
        chapters = chapters[: args.max_chapters]
    print(f"chapters kept (>= {DOC_MIN} chars): {len(chapters)}")

    rows: list[CorpusSegment] = []
    t0 = time.perf_counter()
    for ci, paras in enumerate(chapters, start=1):
        title = paras[0] if (_TITLE_RE.match(paras[0]) and len(paras[0]) <= 30) else None
        body = paras[1:] if title else paras
        boundaries: set[int] = set()
        if not args.no_semantic:
            boundaries = valley_gaps(await embed_texts(body))
        if ci % 10 == 0 or ci == len(chapters):
            done = time.perf_counter() - t0
            eta = done / ci * (len(chapters) - ci)
            print(f"  segmenting {ci}/{len(chapters)} chapters "
                  f"({done:.0f}s elapsed, ~{eta:.0f}s left)", flush=True)
        for si, text in enumerate(segment(body, boundaries), start=1):
            tex = rhythm.texture(text)
            rows.append(
                CorpusSegment(
                    work=args.work,
                    chapter_no=ci,
                    chapter_title=title,
                    seq=si,
                    text=text,
                    char_len=len(text),
                    **tex,
                )
            )

    lens_all = sorted(r.char_len for r in rows)
    if args.dry_run:
        print(f"[dry-run] {len(rows)} segments over {len(chapters)} chapters")
        print(f"[dry-run] segment len min/med/max = "
              f"{lens_all[0]}/{lens_all[len(lens_all) // 2]}/{lens_all[-1]}")
        by_chapter: dict[int, int] = {}
        for r_ in rows:
            by_chapter[r_.chapter_no] = by_chapter.get(r_.chapter_no, 0) + 1
        head = list(by_chapter.items())[:6]
        print(f"[dry-run] segments per chapter (first 6): {head}")
        print("[dry-run] nothing written")
        return

    async with AsyncSessionLocal() as db:
        if args.replace:
            await db.execute(delete(CorpusSegment).where(CorpusSegment.work == args.work))
            await db.commit()
        elif (
            await db.execute(
                select(CorpusSegment.id).where(CorpusSegment.work == args.work).limit(1)
            )
        ).first():
            raise SystemExit(f"work '{args.work}' already ingested; pass --replace")
        for i in range(0, len(rows), 500):
            db.add_all(rows[i : i + 500])
            await db.commit()
            print(f"  {min(i + 500, len(rows))}/{len(rows)}", flush=True)

    lens = [r.char_len for r in rows]
    lens.sort()
    print(
        f"done: {len(rows)} segments over {len(chapters)} chapters, "
        f"{sum(lens)} chars; segment len min/med/max = "
        f"{lens[0]}/{lens[len(lens) // 2]}/{lens[-1]}"
    )


if __name__ == "__main__":
    asyncio.run(main())
