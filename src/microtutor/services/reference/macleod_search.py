"""Two-step Macleod retrieval for Docent coaching.

1) Pick presenting-problem chapter(s) from the table of contents
2) Load that chapter's diagnostic pages (overview / DDx / step-by-step)

Queries use facts already revealed in conversation — never the hidden case package.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.I)
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")

_STOP = frozenset(
    """
    a an the and or of to in on for with from by is are was were be been being
    this that these those it its as at if then than so not no yes do does did
    have has had i you he she we they me my your his her our their what which
    who how when where why can could should would may might will just about
    into over under after before also only very more most other some any all
    """.split()
)

# Prefer these page types when loading a chapter
_STRUCTURE_CUES = (
    ("differential diagnosis", 1.0),
    ("overview", 0.9),
    ("step-by-step", 0.85),
    ("step by-step", 0.85),
    ("key information", 0.5),
    ("clinical tool", 0.4),
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_data_dir() -> Path:
    return _project_root() / "data" / "references" / "macleods"


def tokenize(text: str) -> list[str]:
    return [
        t
        for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) > 2 and t not in _STOP
    ]


@dataclass
class MacleodHit:
    chapter_id: str
    chapter_title: str
    chapter_number: int
    flip_page: int
    book_page: Optional[int]
    score: float
    excerpt: str
    page_role: str = ""

    def cite(self) -> str:
        page_bit = f", p.{self.book_page}" if self.book_page else f", flip p.{self.flip_page}"
        return f"Macleod Ch.{self.chapter_number}{page_bit}"


@dataclass
class MacleodRetrieval:
    """Result of TOC routing + chapter load."""

    selected_chapters: list[dict[str, Any]] = field(default_factory=list)
    hits: list[MacleodHit] = field(default_factory=list)
    route_method: str = "none"  # "llm_toc" | "lexical_toc" | "none"

    def cites(self) -> list[str]:
        return [h.cite() for h in self.hits]

    def format_for_prompt(self) -> str:
        if not self.hits and not self.selected_chapters:
            return ""
        header_parts = []
        if self.selected_chapters:
            titles = ", ".join(
                f"Ch.{c['number']} {c['title']}" for c in self.selected_chapters
            )
            header_parts.append(
                f"TOC route ({self.route_method}): {titles}"
            )
        blocks = list(header_parts)
        for h in self.hits:
            role = f" [{h.page_role}]" if h.page_role else ""
            blocks.append(f"[{h.cite()} — {h.chapter_title}{role}]\n{h.excerpt}")
        return "\n\n---\n\n".join(blocks)


class MacleodSearchService:
    """TOC-first chapter picker + chapter page loader."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        self._lock = threading.Lock()
        self._ready = False
        self.chapters: list[dict[str, Any]] = []
        self.pages: list[dict[str, Any]] = []
        self._idf: dict[str, float] = {}
        self._chapter_by_id: dict[str, dict[str, Any]] = {}
        self._pages_by_chapter: dict[str, list[dict[str, Any]]] = {}

    def ensure_loaded(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            self._load()
            self._ready = True

    def _load(self) -> None:
        chapters_path = self.data_dir / "chapters.json"
        pages_path = self.data_dir / "pages.jsonl"
        if not chapters_path.exists() or not pages_path.exists():
            raise FileNotFoundError(
                f"Macleod reference data missing under {self.data_dir}"
            )

        meta = json.loads(chapters_path.read_text(encoding="utf-8"))
        offset = int(meta.get("book_to_flip_offset", 11))
        raw_chapters = list(meta.get("chapters") or [])
        for i, ch in enumerate(raw_chapters):
            start_book = int(ch["book_start"])
            end_book = (
                int(raw_chapters[i + 1]["book_start"]) - 1
                if i + 1 < len(raw_chapters)
                else 300
            )
            ch["flip_start"] = start_book + offset
            ch["flip_end"] = end_book + offset
            ch["book_end"] = end_book
        self.chapters = raw_chapters
        self._chapter_by_id = {c["id"]: c for c in self.chapters}

        pages: list[dict[str, Any]] = []
        by_ch: dict[str, list[dict[str, Any]]] = {c["id"]: [] for c in self.chapters}
        for line in pages_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            flip = int(row["page"])
            text = (row.get("text") or "").strip()
            if len(text) < 40:
                continue
            chapter = self._chapter_for_flip(flip)
            if not chapter:
                continue
            book_page = flip - offset
            tokens = tokenize(text)
            page = {
                "flip_page": flip,
                "book_page": book_page,
                "chapter_id": chapter["id"],
                "chapter_title": chapter["title"],
                "chapter_number": chapter["number"],
                "text": text,
                "tokens": tokens,
                "tf": self._tf(tokens),
                "page_role": self._page_role(text),
            }
            pages.append(page)
            by_ch[chapter["id"]].append(page)
        self.pages = pages
        self._pages_by_chapter = by_ch

        df: dict[str, int] = {}
        for p in self.pages:
            for tok in set(p["tokens"]):
                df[tok] = df.get(tok, 0) + 1
        n = max(len(self.pages), 1)
        self._idf = {t: math.log(1 + n / (1 + c)) for t, c in df.items()}
        logger.info(
            "Macleod index loaded: %d chapters, %d pages from %s",
            len(self.chapters),
            len(self.pages),
            self.data_dir,
        )

    def _chapter_for_flip(self, flip: int) -> Optional[dict[str, Any]]:
        for ch in self.chapters:
            if ch["flip_start"] <= flip <= ch["flip_end"]:
                return ch
        return None

    @staticmethod
    def _page_role(text: str) -> str:
        low = (text or "").lower()
        if "differential diagnosis" in low:
            return "differential"
        if "overview" in low:
            return "overview"
        if "step-by-step" in low or "step by-step" in low:
            return "step-by-step"
        if "key information" in low:
            return "key-information"
        return "body"

    @staticmethod
    def _tf(tokens: list[str]) -> dict[str, float]:
        if not tokens:
            return {}
        counts: dict[str, int] = {}
        for t in tokens:
            counts[t] = counts.get(t, 0) + 1
        n = float(len(tokens))
        return {t: c / n for t, c in counts.items()}

    def toc_entries(self, *, section2_only: bool = True) -> list[dict[str, Any]]:
        """Compact TOC for LLM / display: presenting problems (+ optional principles)."""
        self.ensure_loaded()
        out = []
        for ch in self.chapters:
            if section2_only and int(ch.get("section", 2)) != 2:
                continue
            out.append(
                {
                    "id": ch["id"],
                    "number": ch["number"],
                    "title": ch["title"],
                    "aliases": list(ch.get("aliases") or []),
                }
            )
        return out

    def format_toc_for_prompt(self, *, section2_only: bool = True) -> str:
        lines = []
        for e in self.toc_entries(section2_only=section2_only):
            alias = ""
            if e["aliases"]:
                alias = f" (aka: {', '.join(e['aliases'][:4])})"
            lines.append(f"- {e['id']}: Ch.{e['number']} {e['title']}{alias}")
        # Always allow principles chapters as secondary picks
        if section2_only:
            for ch in self.chapters:
                if int(ch.get("section", 2)) == 1 and ch["number"] in (2, 3):
                    lines.append(
                        f"- {ch['id']}: Ch.{ch['number']} {ch['title']} [principles]"
                    )
        return "\n".join(lines)

    # ----- Step 1: TOC pick -----

    def select_chapters_lexical(
        self,
        query: str,
        *,
        top_k: int = 2,
        include_principles_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        """Score TOC titles/aliases only (no full-page search)."""
        self.ensure_loaded()
        q = (query or "").strip()
        if not q:
            return []
        q_tokens = set(tokenize(q))
        q_lower = q.lower()
        scored: list[tuple[dict[str, Any], float]] = []

        for ch in self.chapters:
            # Prefer presenting-problem chapters; principles only as soft fallback
            is_presentation = int(ch.get("section", 2)) == 2
            score = 0.0
            for alias in [ch["title"], *(ch.get("aliases") or [])]:
                a = (alias or "").lower().strip()
                if not a:
                    continue
                if a in q_lower:
                    score += 4.0 if is_presentation else 1.5
                    continue
                a_toks = set(tokenize(a))
                if not a_toks:
                    continue
                overlap = len(q_tokens & a_toks) / len(a_toks)
                if overlap >= 0.6:
                    score += (2.5 if is_presentation else 0.8) * overlap
                elif overlap > 0:
                    score += (1.0 if is_presentation else 0.3) * overlap
            if score > 0:
                scored.append((ch, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        picked = [c for c, s in scored[:top_k] if s >= 0.8]

        if not picked and include_principles_fallback:
            # Generic approach help → diagnostic process
            method = self._chapter_by_id.get("ch3_diagnostic_process")
            if method:
                picked = [method]
        return picked

    def resolve_chapter_ids(self, chapter_ids: list[str]) -> list[dict[str, Any]]:
        self.ensure_loaded()
        out: list[dict[str, Any]] = []
        seen = set()
        for cid in chapter_ids or []:
            key = (cid or "").strip()
            ch = self._chapter_by_id.get(key)
            if not ch and key.isdigit():
                # allow "14" → ch14_fever etc.
                for c in self.chapters:
                    if str(c["number"]) == key:
                        ch = c
                        break
            if ch and ch["id"] not in seen:
                out.append(ch)
                seen.add(ch["id"])
        return out

    # ----- Step 2: load chapter pages -----

    def load_chapter_guidance(
        self,
        chapters: list[dict[str, Any]],
        *,
        pages_per_chapter: int = 3,
        max_excerpt_chars: int = 1600,
    ) -> list[MacleodHit]:
        """Load overview / DDx / step-by-step pages from selected chapters."""
        self.ensure_loaded()
        hits: list[MacleodHit] = []
        for ch in chapters:
            pages = list(self._pages_by_chapter.get(ch["id"]) or [])
            if not pages:
                continue
            ranked: list[tuple[float, dict[str, Any]]] = []
            for p in pages:
                role = p.get("page_role") or "body"
                role_score = {
                    "differential": 1.0,
                    "overview": 0.95,
                    "step-by-step": 0.9,
                    "key-information": 0.55,
                    "body": 0.15,
                }.get(role, 0.1)
                # Prefer earlier pages within a chapter (overview usually first)
                position = 1.0 / (1.0 + 0.05 * max(0, p["book_page"] - int(ch["book_start"])))
                ranked.append((role_score + 0.1 * position, p))
            ranked.sort(key=lambda x: x[0], reverse=True)

            # Ensure diversity of roles when possible
            chosen_pages: list[dict[str, Any]] = []
            seen_roles: set[str] = set()
            for _, p in ranked:
                role = p.get("page_role") or "body"
                if role in seen_roles and role != "step-by-step":
                    continue
                chosen_pages.append(p)
                seen_roles.add(role)
                if len(chosen_pages) >= pages_per_chapter:
                    break
            if len(chosen_pages) < pages_per_chapter:
                for _, p in ranked:
                    if p in chosen_pages:
                        continue
                    chosen_pages.append(p)
                    if len(chosen_pages) >= pages_per_chapter:
                        break

            for p in chosen_pages:
                excerpt = p["text"]
                if len(excerpt) > max_excerpt_chars:
                    excerpt = excerpt[:max_excerpt_chars].rsplit(" ", 1)[0] + "…"
                hits.append(
                    MacleodHit(
                        chapter_id=ch["id"],
                        chapter_title=ch["title"],
                        chapter_number=ch["number"],
                        flip_page=p["flip_page"],
                        book_page=p["book_page"],
                        score=1.0,
                        excerpt=excerpt,
                        page_role=p.get("page_role") or "",
                    )
                )
        return hits

    def retrieve_two_step(
        self,
        query: str,
        *,
        chapter_ids: Optional[list[str]] = None,
        top_chapters: int = 2,
        pages_per_chapter: int = 3,
        route_method: str = "lexical_toc",
    ) -> MacleodRetrieval:
        """
        Two-step retrieval.

        If chapter_ids provided (e.g. from LLM TOC pick), use those.
        Else lexically pick from TOC, then load chapter guidance pages.
        """
        self.ensure_loaded()
        if chapter_ids:
            chapters = self.resolve_chapter_ids(chapter_ids)
            method = route_method or "llm_toc"
        else:
            chapters = self.select_chapters_lexical(query, top_k=top_chapters)
            method = "lexical_toc"

        # Always add a thin principles page if only presentation chapters
        if chapters and all(int(c.get("section", 2)) == 2 for c in chapters):
            method_ch = self._chapter_by_id.get("ch3_diagnostic_process")
            # Don't force-load all of ch3 — coach prompt already has method rules.
            _ = method_ch

        hits = self.load_chapter_guidance(
            chapters, pages_per_chapter=pages_per_chapter
        )
        return MacleodRetrieval(
            selected_chapters=chapters,
            hits=hits,
            route_method=method,
        )

    # Back-compat wrapper
    def search(self, query: str, *, k: int = 4, prefer_section2: bool = True) -> list[MacleodHit]:
        pages_per = max(1, k // 2)
        result = self.retrieve_two_step(
            query, top_chapters=2, pages_per_chapter=pages_per
        )
        return result.hits[:k]

    def format_for_prompt(self, hits: list[MacleodHit]) -> str:
        return MacleodRetrieval(hits=hits).format_for_prompt()


def build_query_from_conversation(
    conversation_history: list[dict[str, Any]],
    student_message: str,
    *,
    max_chars: int = 2500,
) -> str:
    """Build a retrieval query from revealed dialogue only (not case package)."""
    parts: list[str] = []
    if student_message:
        parts.append(student_message.strip())
    for msg in conversation_history or []:
        role = (msg.get("role") or "").strip()
        content = (msg.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        if content.startswith("Welcome to today's case"):
            continue
        parts.append(content[:600])
    joined = "\n".join(parts)
    if len(joined) > max_chars:
        joined = joined[-max_chars:]
    return joined


def parse_toc_pick_response(text: str) -> list[str]:
    """Parse LLM TOC picker JSON → chapter ids."""
    if not text:
        return []
    raw = text.strip()
    m = _JSON_BLOCK_RE.search(raw)
    if m:
        raw = m.group(0)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # fall back: bare ids on lines
        ids = re.findall(r"ch\d+_[a-z0-9_]+", text.lower())
        return ids[:3]
    ids = data.get("chapter_ids") or data.get("chapters") or []
    if isinstance(ids, str):
        ids = [ids]
    out = []
    for item in ids:
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict) and item.get("id"):
            out.append(str(item["id"]).strip())
    return out[:3]


_SERVICE: Optional[MacleodSearchService] = None
_SERVICE_LOCK = threading.Lock()


def get_macleod_search() -> MacleodSearchService:
    global _SERVICE
    if _SERVICE is None:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = MacleodSearchService()
    return _SERVICE
