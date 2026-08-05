"""Parse [[speaker:...]] markers from patient/module agent replies."""

from __future__ import annotations

import re
from typing import Optional

from microtutor.services.case.figure_catalog import parse_display_figures

VALID_SPEAKERS = frozenset({"patient", "family", "nurse", "tutor"})

_SPEAKER_RE = re.compile(
    r"\[\[\s*speaker\s*:\s*(patient|family|nurse|tutor)\s*\]\]",
    re.IGNORECASE,
)


def parse_speaker(text: str, *, default: str = "patient") -> tuple[str, str]:
    """Strip speaker markers; return (cleaned_text, speaker_id)."""
    if not text:
        return "", default

    found: list[str] = []
    for m in _SPEAKER_RE.finditer(text):
        found.append(m.group(1).lower())

    cleaned = _SPEAKER_RE.sub("", text)
    cleaned = re.sub(r"^[ \t]+", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    speaker = found[0] if found else default
    if speaker not in VALID_SPEAKERS:
        speaker = default
    return cleaned, speaker


def parse_agent_markers(
    text: str,
    *,
    allowed_figure_numbers: Optional[set[int]] = None,
    default_speaker: str = "patient",
) -> tuple[str, str, list[int]]:
    """Strip [[speaker:…]] then [[display_figure:N]]; return clean text, speaker, figures."""
    after_speaker, speaker = parse_speaker(text, default=default_speaker)
    clean, figures = parse_display_figures(
        after_speaker,
        allowed_numbers=allowed_figure_numbers,
    )
    return clean, speaker, figures
