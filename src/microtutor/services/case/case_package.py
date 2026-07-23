"""Bind case narrative + figures into one session package.

Fixes the mismatch where the patient agent used organism-cached/RAG text while
the UI attached figures from a different case_library entry.
"""

from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from microtutor.services.case.case_loader import get_case

logger = logging.getLogger(__name__)


@dataclass
class CasePackage:
    """One session's bound clinical case + media."""

    organism: str
    narrative: str
    source: str  # "case_library" | "organism_cache" | "generated"
    library_case_id: Optional[str] = None
    figures: list[str] = field(default_factory=list)
    title: Optional[str] = None

    @property
    def has_figures(self) -> bool:
        return bool(self.library_case_id and self.figures)


def narrative_from_library_case(case: dict[str, Any]) -> str:
    """Build patient/tutor case text from a library entry.

    Uses history + exam/studies (where figure references live). Omits diagnosis
    so the patient agent cannot recite the answer.
    """
    parts: list[str] = []
    title = (case.get("title") or "").strip()
    if title:
        parts.append(f"Case title: {title}")
    history = (case.get("history") or "").strip()
    if history:
        parts.append("=== HISTORY ===\n" + history)
    exam = (case.get("exam_studies") or "").strip()
    if exam:
        parts.append("=== EXAMINATION AND STUDIES ===\n" + exam)
    # Keep a short teaching footnote for tutors without naming the organism diagnosis
    more = (case.get("more_info") or "").strip()
    if more:
        # Truncate — more_info is often reference dumps
        snippet = more[:800] + ("…" if len(more) > 800 else "")
        parts.append("=== ADDITIONAL CONTEXT (for educator; do not volunteer) ===\n" + snippet)
    return "\n\n".join(parts).strip()


def _package_from_library_case(
    library_case: dict[str, Any],
    *,
    organism: Optional[str] = None,
) -> CasePackage:
    from microtutor.api.routes.cases import organism_from_library_case

    org = (organism or organism_from_library_case(library_case) or "").strip().lower()
    if not org:
        org = (library_case.get("id") or "unknown").strip().lower()

    narrative = narrative_from_library_case(library_case)
    if not narrative:
        raise ValueError(
            f"Library case {library_case.get('id')!r} has no usable history/exam text"
        )

    pkg = CasePackage(
        organism=org,
        narrative=narrative,
        source="case_library",
        library_case_id=library_case.get("id"),
        figures=list(library_case.get("figures") or []),
        title=library_case.get("title"),
    )
    logger.info(
        "Bound case package organism=%r library_id=%s figures=%d",
        org,
        pkg.library_case_id,
        len(pkg.figures),
    )
    return pkg


def resolve_case_package_by_id(library_case_id: str) -> CasePackage:
    """Resolve a bound package for an explicit case_library id (e.g. Case_02032)."""
    from microtutor.api.routes.cases import get_library_case

    case_id = (library_case_id or "").strip()
    if not case_id:
        raise ValueError("library_case_id is required")

    library_case = get_library_case(case_id)
    if not library_case:
        raise ValueError(f"Case library entry {case_id!r} not found")

    return _package_from_library_case(library_case)


def resolve_case_package(
    organism: str,
    *,
    prefer_figures: bool = True,
    randomize: bool = True,
) -> CasePackage:
    """Resolve a bound package for an organism.

    Prefer a case_library entry that has figures so narrative and images match.
    Fall back to organism cache / RAG text with no figures.

    When ``randomize`` is False, pick the first match (stable / reproducible).
    """
    organism = (organism or "").strip()
    library_case: Optional[dict[str, Any]] = None

    try:
        from microtutor.api.routes.cases import lookup_cases_by_organism

        matches = lookup_cases_by_organism(organism)
        if matches:
            with_figs = [c for c in matches if c.get("figures")]
            pool = with_figs if (prefer_figures and with_figs) else matches
            library_case = random.choice(pool) if randomize else pool[0]
    except Exception as e:
        logger.warning("Case library lookup failed for %r: %s", organism, e)

    if library_case:
        try:
            return _package_from_library_case(library_case, organism=organism)
        except ValueError:
            pass

    # Fallback: organism vignette / generated case (no guaranteed figures)
    narrative = get_case(organism)
    return CasePackage(
        organism=organism,
        narrative=narrative,
        source="organism_cache",
        library_case_id=None,
        figures=[],
        title=None,
    )


class CasePackageStore:
    """In-memory package store keyed by client session case_id."""

    def __init__(self) -> None:
        self._packages: dict[str, CasePackage] = {}
        self._lock = threading.Lock()

    def put(self, session_case_id: str, package: CasePackage) -> CasePackage:
        with self._lock:
            self._packages[session_case_id] = package
            return package

    def get(self, session_case_id: str) -> Optional[CasePackage]:
        with self._lock:
            return self._packages.get(session_case_id)

    def get_narrative(self, session_case_id: str) -> Optional[str]:
        pkg = self.get(session_case_id)
        return pkg.narrative if pkg else None


_store: Optional[CasePackageStore] = None
_store_lock = threading.Lock()


def get_case_package_store() -> CasePackageStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = CasePackageStore()
        return _store
