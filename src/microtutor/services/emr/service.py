"""Session-scoped EMR extraction with background queue (src_simplified style).

Each case_id gets its own note list and worker. Extraction runs off the chat
critical path; the frontend polls for updates.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from queue import Empty, Queue
from typing import Any, Optional

from microtutor.core.config.config_helper import config
from microtutor.core.llm.llm_client import LLMClient
from microtutor.prompts.emr_prompts import (
    get_emr_full_rebuild_prompt,
    get_emr_note_extraction_prompt,
)

logger = logging.getLogger(__name__)

# Map extraction sections → DocentID EMR panel field keys
SECTION_TO_FIELD: dict[str, str] = {
    "HPI": "hpi",
    "PMH": "pmh",
    "Medications": "medications",
    "Allergies": "allergies",
    "Social History": "social_history",
    "Family History": "family_history",
    "Epidemiological History": "social_history",
    "Physical Exam": "exam",
    "Vitals": "vitals",
    "Bedside": "special_tests",
    "Bloods": "labs",
    "Imaging": "imaging",
    "Microbiology": "microbiology",
    "Special": "special_tests",
}


def notes_to_emr_data(notes: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse structured notes into the EMR panel's field → text/list map."""
    buckets: dict[str, list[str]] = {}
    for note in notes:
        if not isinstance(note, dict):
            continue
        section = (note.get("section") or "").strip()
        content = (note.get("content") or "").strip()
        if not section or not content:
            continue
        field = SECTION_TO_FIELD.get(section)
        if not field:
            # Unknown section → other
            field = "other"
        buckets.setdefault(field, [])
        if content not in buckets[field]:
            buckets[field].append(content)

    result: dict[str, Any] = {}
    for field, items in buckets.items():
        result[field] = items if len(items) > 1 else items[0]
    return result


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse LLM JSON, tolerating optional markdown fences."""
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            data = json.loads(fence.group(1).strip())
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    return {}


class _EmrCaseSession:
    """In-memory EMR state + worker for one case_id."""

    def __init__(self, case_id: str, llm_client: LLMClient):
        self.case_id = case_id
        self.llm_client = llm_client
        self.emr_notes: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._queue: Queue[tuple[str, str, Optional[str]]] = Queue()
        self._busy = threading.Event()
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name=f"emr-{case_id[:24]}"
        )
        self._worker.start()

    def enqueue(
        self,
        student_question: str,
        patient_response: str,
        image_url: Optional[str] = None,
    ) -> None:
        self._queue.put((student_question, patient_response, image_url))

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.emr_notes)

    def is_busy(self) -> bool:
        return self._busy.is_set() or not self._queue.empty()

    def rebuild_from_history(self, history: list[dict[str, str]]) -> list[dict[str, Any]]:
        """Replace notes with a full re-extraction from conversation history."""
        self._busy.set()
        try:
            turns: list[str] = []
            hist = list(history or [])
            i = 0
            while i < len(hist):
                role = hist[i].get("role")
                content = hist[i].get("content", "")
                if role == "assistant" and (i == 0 or hist[i - 1].get("role") != "user"):
                    turns.append(
                        f"Student: (Patient introduces themselves)\nPatient: {content}"
                    )
                    i += 1
                elif (
                    i + 1 < len(hist)
                    and role == "user"
                    and hist[i + 1].get("role") == "assistant"
                ):
                    turns.append(
                        f"Student: {content}\nPatient: {hist[i + 1].get('content', '')}"
                    )
                    i += 2
                else:
                    i += 1

            if not turns:
                with self._lock:
                    self.emr_notes = []
                return []

            conversation_text = "\n\n".join(turns)
            prompt = get_emr_full_rebuild_prompt().format(conversation=conversation_text)
            raw = self.llm_client.generate(
                messages=[{"role": "user", "content": prompt}],
                model=config.API_MODEL_NAME,
                tools=None,
                retries=2,
                response_format={"type": "json_object"},
            )
            if not raw or not isinstance(raw, str):
                return self.snapshot()

            data = _parse_json_object(raw)
            new_notes = data.get("notes", [])
            if not isinstance(new_notes, list):
                return self.snapshot()

            valid = [
                n
                for n in new_notes
                if isinstance(n, dict) and n.get("section") and n.get("content")
            ]
            with self._lock:
                self.emr_notes = valid
            logger.info(
                "[EMR] Full rebuild case_id=%s notes=%d from %d turns",
                self.case_id,
                len(valid),
                len(turns),
            )
            return valid
        except Exception as e:
            logger.error("[EMR] Rebuild failed case_id=%s: %s", self.case_id, e, exc_info=True)
            return self.snapshot()
        finally:
            self._busy.clear()

    def _worker_loop(self) -> None:
        while True:
            first = self._queue.get()
            batch: list[tuple[str, str, Optional[str]]] = [first]
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except Empty:
                    break

            self._busy.set()
            try:
                self._extract_batch(batch)
            except Exception as e:
                logger.error(
                    "[EMR] Worker error case_id=%s: %s", self.case_id, e, exc_info=True
                )
            finally:
                self._busy.clear()
                for _ in batch:
                    self._queue.task_done()

    def _extract_batch(self, batch: list[tuple[str, str, Optional[str]]]) -> None:
        exchanges = "\n\n".join(
            f"--- Exchange {i + 1} ---\nStudent: {q}\nPatient: {a}"
            for i, (q, a, _) in enumerate(batch)
        )
        image_urls = [url for _, _, url in batch if url]

        with self._lock:
            existing = list(self.emr_notes)

        existing_text = json.dumps(existing, indent=2) if existing else "None yet."
        prompt = get_emr_note_extraction_prompt().format(
            student_question=exchanges,
            patient_response="(see exchanges above)",
            existing_notes=existing_text,
        )
        raw = self.llm_client.generate(
            messages=[{"role": "user", "content": prompt}],
            model=config.API_MODEL_NAME,
            tools=None,
            retries=2,
            response_format={"type": "json_object"},
        )
        if not raw or not isinstance(raw, str):
            logger.warning("[EMR] Empty extraction response case_id=%s", self.case_id)
            return

        data = _parse_json_object(raw)
        new_notes = data.get("notes", [])
        if not isinstance(new_notes, list):
            return

        img_idx = 0
        with self._lock:
            for note in new_notes:
                if not (
                    isinstance(note, dict)
                    and note.get("section")
                    and note.get("content")
                ):
                    continue
                if img_idx < len(image_urls):
                    note["image_url"] = image_urls[img_idx]
                    img_idx += 1
                self.emr_notes.append(note)

        logger.info(
            "[EMR] Extracted %d new notes (batch=%d) case_id=%s total=%d",
            len(new_notes),
            len(batch),
            self.case_id,
            len(self.emr_notes),
        )


class EmrNotesService:
    """Process-wide registry of per-case EMR sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, _EmrCaseSession] = {}
        self._lock = threading.Lock()
        self._llm = LLMClient(model=config.API_MODEL_NAME)

    def start_case(self, case_id: str) -> _EmrCaseSession:
        with self._lock:
            session = _EmrCaseSession(case_id, self._llm)
            self._sessions[case_id] = session
            return session

    def get_session(self, case_id: str) -> Optional[_EmrCaseSession]:
        with self._lock:
            return self._sessions.get(case_id)

    def ensure_session(self, case_id: str) -> _EmrCaseSession:
        with self._lock:
            session = self._sessions.get(case_id)
            if session is None:
                session = _EmrCaseSession(case_id, self._llm)
                self._sessions[case_id] = session
            return session

    def enqueue_exchange(
        self,
        case_id: str,
        student_question: str,
        patient_response: str,
        image_url: Optional[str] = None,
    ) -> None:
        self.ensure_session(case_id).enqueue(
            student_question, patient_response, image_url
        )

    def get_notes(self, case_id: str) -> list[dict[str, Any]]:
        session = self.get_session(case_id)
        return session.snapshot() if session else []

    def is_busy(self, case_id: str) -> bool:
        session = self.get_session(case_id)
        return session.is_busy() if session else False

    def rebuild(
        self, case_id: str, history: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        return self.ensure_session(case_id).rebuild_from_history(history)


_emr_service: Optional[EmrNotesService] = None
_emr_service_lock = threading.Lock()


def get_emr_service() -> EmrNotesService:
    global _emr_service
    with _emr_service_lock:
        if _emr_service is None:
            _emr_service = EmrNotesService()
        return _emr_service
