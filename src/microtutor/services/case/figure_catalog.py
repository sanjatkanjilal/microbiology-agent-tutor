"""Figure catalog for LLM-driven reveal (replaces frontend keyword heuristics)."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MASTER_PATH = _REPO_ROOT / "data" / "cases" / "figure_descriptions.json"
_ALL_CASES = _REPO_ROOT / "data" / "cases" / "ID_Images" / "All_cases"

_CAPTION_RE = re.compile(r"Figure\s+(\d+)\.\s*([^\n]{3,400})", re.IGNORECASE)
_DISPLAY_RE = re.compile(
    r"\[\[\s*display_figure\s*:\s*(\d+)\s*\]\]",
    re.IGNORECASE,
)
_DISPLAY_PAREN_RE = re.compile(
    r"\bdisplay_figure\s*\(\s*(\d+)\s*\)",
    re.IGNORECASE,
)
_PLACEHOLDER_CAPTION_RE = re.compile(
    r"^(image|physical finding|physical findings|see text)\.?$",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _load_master_descriptions() -> dict[str, Any]:
    if not _MASTER_PATH.exists():
        logger.warning("figure_descriptions.json not found at %s", _MASTER_PATH)
        return {}
    try:
        with open(_MASTER_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to load figure_descriptions.json: %s", e)
        return {}


def reload_figure_descriptions() -> None:
    """Clear cached master file (e.g. after a batch caption run)."""
    _load_master_descriptions.cache_clear()


def _figure_number_from_filename(filename: str) -> Optional[int]:
    m = re.match(r"figure(\d+)\.", filename or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def _usable_caption(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned or _PLACEHOLDER_CAPTION_RE.match(cleaned):
        return None
    return cleaned


def _captions_from_narrative(narrative: str) -> dict[int, str]:
    return {
        int(m.group(1)): m.group(2).strip()
        for m in _CAPTION_RE.finditer(narrative or "")
    }


def _record_for(
    library_case_id: str,
    filename: str,
    master: dict[str, Any],
) -> Optional[dict[str, Any]]:
    key = f"{library_case_id}/{filename}"
    rec = master.get(key)
    if isinstance(rec, dict):
        return rec
    # Per-case sidecar written by describe_case_figures.py
    sidecar = _ALL_CASES / library_case_id / "figures_meta.json"
    if sidecar.exists():
        try:
            with open(sidecar, encoding="utf-8") as f:
                meta = json.load(f)
            rec = meta.get(key)
            if isinstance(rec, dict):
                return rec
        except Exception:  # noqa: BLE001
            pass
    return None


def build_figure_catalog(
    library_case_id: Optional[str],
    figures: list[str],
    *,
    narrative: str = "",
) -> list[dict[str, Any]]:
    """Build compact per-figure entries for the patient prompt + reveal validation."""
    if not library_case_id or not figures:
        return []

    master = _load_master_descriptions()
    narrative_caps = _captions_from_narrative(narrative)
    catalog: list[dict[str, Any]] = []

    for filename in figures:
        n = _figure_number_from_filename(filename)
        if n is None:
            continue
        rec = _record_for(library_case_id, filename, master) or {}
        desc = rec.get("description") if isinstance(rec.get("description"), dict) else {}
        source_caption = _usable_caption(rec.get("source_caption")) or _usable_caption(
            narrative_caps.get(n)
        )

        short = _usable_caption(desc.get("short_caption")) or source_caption
        modality = (desc.get("modality") or "").strip() or None
        site = (desc.get("anatomical_site") or "").strip() or None
        keywords = list(desc.get("keywords") or [])[:8]
        triggers = list(desc.get("reveal_triggers") or [])[:8]
        detail = _usable_caption(desc.get("detailed_description"))
        if detail and len(detail) > 280:
            detail = detail[:277] + "…"

        # Always include an entry so the model knows figure N exists.
        if not short:
            short = f"Case figure {n} (see case text references)"

        catalog.append(
            {
                "figure_number": n,
                "filename": filename,
                "modality": modality,
                "anatomical_site": site,
                "short_caption": short,
                "detailed_description": detail,
                "keywords": keywords,
                "reveal_triggers": triggers,
                "has_vision_description": bool(desc),
            }
        )

    catalog.sort(key=lambda e: e["figure_number"])
    return catalog


def format_figure_catalog_for_prompt(catalog: list[dict[str, Any]]) -> str:
    """Compact block injected into the patient system prompt."""
    if not catalog:
        return ""

    lines = [
        "=== AVAILABLE CASE FIGURES (for reveal only — do not invent images) ===",
        "When the student asks to examine / view / order something that matches a figure below,",
        "use marker order: [[speaker:…]] first, then [[display_figure:N]] if applicable, then text.",
        "Use at most ONE figure per reply unless they clearly ask for multiple related images.",
        "Do NOT reveal figures for plain history questions (e.g. 'any rashes?') — only when they",
        "request exam inspection, imaging review, or a lab/microscopy result that the figure shows.",
        "If nothing matches, do not emit a display_figure marker.",
        "",
    ]
    for entry in catalog:
        n = entry["figure_number"]
        modality = entry.get("modality") or "image"
        site = entry.get("anatomical_site")
        head = f"Figure {n} ({modality}"
        if site:
            head += f", {site}"
        head += f"): {entry['short_caption']}"
        lines.append(head)
        triggers = entry.get("reveal_triggers") or []
        keywords = entry.get("keywords") or []
        hints = triggers or keywords
        if hints:
            lines.append("  unlock when student asks about: " + ", ".join(hints[:6]))
    return "\n".join(lines)


def parse_display_figures(
    text: str,
    *,
    allowed_numbers: Optional[set[int]] = None,
) -> tuple[str, list[int]]:
    """Strip display_figure markers; return cleaned text + validated figure numbers."""
    if not text:
        return "", []

    found: list[int] = []
    for m in _DISPLAY_RE.finditer(text):
        found.append(int(m.group(1)))
    for m in _DISPLAY_PAREN_RE.finditer(text):
        found.append(int(m.group(1)))

    cleaned = _DISPLAY_RE.sub("", text)
    cleaned = _DISPLAY_PAREN_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    revealed: list[int] = []
    seen: set[int] = set()
    for n in found:
        if n in seen:
            continue
        if allowed_numbers is not None and n not in allowed_numbers:
            logger.info("Ignoring out-of-range display_figure:%s", n)
            continue
        seen.add(n)
        revealed.append(n)

    return cleaned, revealed


def allowed_figure_numbers(figures: list[str]) -> set[int]:
    nums: set[int] = set()
    for f in figures or []:
        n = _figure_number_from_filename(f)
        if n is not None:
            nums.add(n)
    return nums
