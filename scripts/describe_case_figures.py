#!/usr/bin/env python3
"""Generate detailed vision descriptions for ID case figures via Azure OpenAI.

Scans data/cases/ID_Images/All_cases/Case_*/figure*.jpg, sends each image to a
vision-capable Azure deployment with N concurrent workers, and writes structured
JSON that can later drive LLM figure reveal (instead of keyword heuristics).

Outputs (resumable):
  - data/cases/figure_descriptions.json
      master index keyed by "Case_XXXX/figureN.jpg"
  - data/cases/ID_Images/All_cases/Case_XXXX/figures_meta.json
      per-case sidecar with the same records for that case

Usage:
  # smoke test one image
  python scripts/describe_case_figures.py --limit 1 --workers 1

  # full run (resume-safe; skips keys already present unless --force)
  python scripts/describe_case_figures.py --workers 8 --model gpt-4o-1120

  # only cases missing text captions in case_library.json
  python scripts/describe_case_figures.py --missing-captions-only

Env (from .env / dot_env_microtutor.txt):
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION
  AZURE_OPENAI_DEPLOYMENT_NAME (default model if --model omitted)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncAzureOpenAI, RateLimitError, APIStatusError

REPO_ROOT = Path(__file__).resolve().parent.parent
ALL_CASES = REPO_ROOT / "data" / "cases" / "ID_Images" / "All_cases"
CASE_LIBRARY = REPO_ROOT / "data" / "cases" / "case_library.json"
MASTER_OUT = REPO_ROOT / "data" / "cases" / "figure_descriptions.json"

FIGURE_RE = re.compile(r"^figure(\d+)\.(jpe?g|png|webp|gif)$", re.IGNORECASE)
CAPTION_RE = re.compile(r"Figure\s+(\d+)\.\s*([^\n]{3,400})", re.IGNORECASE)
PLACEHOLDER_CAPTION_RE = re.compile(
    r"^(image|physical finding|physical findings|see text)\.?$",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """\
You are a clinical infectious-diseases image cataloguer for a medical education tutor.
Describe ONLY what is visible in the image. Do not invent laboratory values or history \
not supported by the image. Do not name a definitive organism unless the image itself \
(e.g. a labeled stain/culture) makes that identity visually clear; prefer morphologic \
description otherwise.

Return a single JSON object with this exact schema:
{
  "modality": "clinical photograph | chest radiograph | CT | MRI | ultrasound | \
gram stain | other stain | histopathology | culture plate | endoscopy | ECG | other",
  "anatomical_site": "short phrase or null",
  "short_caption": "one-line caption suitable for a figure legend (max ~20 words)",
  "detailed_description": "2-6 sentences: composition, key findings, laterality if clear, \
technique cues (contrast, stain type, magnification if inferable)",
  "visible_findings": ["bullet findings, concrete and visual"],
  "keywords": ["lowercase retrieval keywords: modality, body part, lesion type, technique"],
  "reveal_triggers": ["phrases a student might say that should unlock this figure, \
e.g. 'skin exam', 'chest x-ray', 'gram stain of sputum'"],
  "contains_phi_redaction": true/false,
  "confidence": 0.0-1.0
}
"""


def load_env() -> None:
    for name in (".env", "dot_env_microtutor.txt"):
        path = REPO_ROOT / name
        if path.exists():
            load_dotenv(dotenv_path=str(path), override=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def image_to_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def extract_library_captions() -> dict[str, dict[int, str]]:
    """case_id -> {figure_number: caption text from library narrative}."""
    if not CASE_LIBRARY.exists():
        return {}
    library = load_json(CASE_LIBRARY, [])
    out: dict[str, dict[int, str]] = {}
    for case in library:
        case_id = case.get("id")
        if not case_id:
            continue
        blob = "\n".join(
            [
                case.get("history") or "",
                case.get("exam_studies") or "",
                case.get("diagnosis") or "",
                case.get("more_info") or "",
            ]
        )
        caps = {
            int(m.group(1)): m.group(2).strip()
            for m in CAPTION_RE.finditer(blob)
        }
        if caps:
            out[case_id] = caps
    return out


def extract_case_text_captions(case_dir: Path) -> dict[int, str]:
    text_path = case_dir / "case_text.txt"
    if not text_path.exists():
        return {}
    blob = text_path.read_text(encoding="utf-8", errors="replace")
    return {
        int(m.group(1)): m.group(2).strip()
        for m in CAPTION_RE.finditer(blob)
    }


@dataclass(frozen=True)
class FigureJob:
    case_id: str
    figure_number: int
    filename: str
    image_path: Path
    key: str
    source_caption: str | None


def discover_jobs(
    *,
    case_filter: str | None,
    missing_captions_only: bool,
    library_captions: dict[str, dict[int, str]],
) -> list[FigureJob]:
    if not ALL_CASES.is_dir():
        raise SystemExit(f"Case image directory not found: {ALL_CASES}")

    jobs: list[FigureJob] = []
    for case_dir in sorted(ALL_CASES.iterdir()):
        if not case_dir.is_dir() or not case_dir.name.startswith("Case_"):
            continue
        case_id = case_dir.name
        if case_filter and case_id != case_filter:
            continue

        text_caps = extract_case_text_captions(case_dir)
        lib_caps = library_captions.get(case_id, {})

        for image_path in sorted(case_dir.iterdir()):
            if not image_path.is_file():
                continue
            m = FIGURE_RE.match(image_path.name)
            if not m:
                continue
            n = int(m.group(1))
            source = lib_caps.get(n) or text_caps.get(n)
            source_usable = None
            if source and not PLACEHOLDER_CAPTION_RE.match(source.strip()):
                source_usable = source.strip()

            if missing_captions_only and source_usable:
                continue

            jobs.append(
                FigureJob(
                    case_id=case_id,
                    figure_number=n,
                    filename=image_path.name,
                    image_path=image_path,
                    key=f"{case_id}/{image_path.name}",
                    source_caption=source_usable,
                )
            )
    return jobs


def parse_model_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


class ContentPolicyBlocked(Exception):
    """Azure content safety rejected the image; do not retry."""


def _is_content_policy_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "content_policy" in text or "content safety" in text or "responsibleaipolicyviolation" in text


def build_messages(job: FigureJob, *, detail: str) -> list[dict[str, Any]]:
    user_bits = [
        f"Case ID: {job.case_id}",
        f"Figure number: {job.figure_number}",
        f"Filename: {job.filename}",
        "This is a de-identified medical education image from an infectious-diseases case library.",
    ]
    if job.source_caption:
        user_bits.append(
            "Existing case-text caption (may be incomplete; verify against the image): "
            + job.source_caption
        )
    user_bits.append(
        "Produce the JSON description for this image. "
        "Prefer visual truth over the existing caption if they conflict."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "\n".join(user_bits)},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_to_data_url(job.image_path),
                        "detail": detail,
                    },
                },
            ],
        },
    ]


async def describe_one(
    client: AsyncAzureOpenAI,
    model: str,
    job: FigureJob,
    *,
    max_retries: int = 5,
    image_detail: str = "high",
) -> dict[str, Any]:
    delay = 2.0
    last_err: Exception | None = None
    # Retry once with lower detail if high detail hits content policy (sometimes helps).
    detail_attempts = [image_detail]
    if image_detail != "low":
        detail_attempts.append("low")

    for detail in detail_attempts:
        messages = build_messages(job, detail=detail)
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1200,
                    response_format={"type": "json_object"},
                )
                content = (resp.choices[0].message.content or "").strip()
                if not content:
                    raise ValueError("empty model content")
                parsed = parse_model_json(content)
                usage = getattr(resp, "usage", None)
                return {
                    "case_id": job.case_id,
                    "filename": job.filename,
                    "figure_number": job.figure_number,
                    "image_path": str(job.image_path.relative_to(REPO_ROOT)),
                    "source_caption": job.source_caption,
                    "description": parsed,
                    "model": model,
                    "image_detail": detail,
                    "generated_at": utc_now(),
                    "usage": {
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    }
                    if usage
                    else None,
                }
            except Exception as e:  # noqa: BLE001
                last_err = e
                if _is_content_policy_error(e):
                    # Try next detail level if available; else surface as blocked.
                    break
                status = getattr(e, "status_code", None)
                retryable = isinstance(
                    e, (RateLimitError, TimeoutError, json.JSONDecodeError, ValueError)
                ) or (isinstance(e, APIStatusError) and status in {408, 429, 500, 502, 503, 504})
                if not retryable or attempt == max_retries:
                    raise
                await asyncio.sleep(delay)
                delay = min(delay * 1.8, 45.0)
        else:
            continue
        # content-policy break -> try next detail
        continue

    if last_err and _is_content_policy_error(last_err):
        raise ContentPolicyBlocked(str(last_err)) from last_err
    raise RuntimeError(f"failed after retries: {last_err}")


class Progress:
    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.ok = 0
        self.failed = 0
        self.lock = asyncio.Lock()
        self.t0 = time.time()

    async def tick(self, success: bool, key: str, err: str | None = None) -> None:
        async with self.lock:
            self.done += 1
            if success:
                self.ok += 1
                status = "ok"
            else:
                self.failed += 1
                status = f"FAIL ({err})"
            elapsed = time.time() - self.t0
            rate = self.done / elapsed if elapsed > 0 else 0
            print(
                f"[{self.done}/{self.total}] {status}  {key}  "
                f"({rate:.2f}/s, {self.ok} ok, {self.failed} failed)",
                flush=True,
            )


def _write_case_sidecar(master: dict[str, Any], case_id: str) -> None:
    case_meta_path = ALL_CASES / case_id / "figures_meta.json"
    case_meta = {k: v for k, v in master.items() if k.startswith(f"{case_id}/")}
    atomic_write_json(case_meta_path, case_meta)


def _record_is_done(record: Any, *, retry_errors: bool) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("description"):
        return True
    if record.get("error") and not retry_errors:
        return True
    return False


async def worker(
    queue: asyncio.Queue[FigureJob | None],
    client: AsyncAzureOpenAI,
    model: str,
    master: dict[str, Any],
    master_lock: asyncio.Lock,
    progress: Progress,
    write_every: int,
    image_detail: str,
) -> None:
    processed_since_flush = 0
    while True:
        job = await queue.get()
        try:
            if job is None:
                return
            try:
                record = await describe_one(
                    client, model, job, image_detail=image_detail
                )
                async with master_lock:
                    master[job.key] = record
                    _write_case_sidecar(master, job.case_id)
                    processed_since_flush += 1
                    if processed_since_flush >= write_every:
                        atomic_write_json(MASTER_OUT, master)
                        processed_since_flush = 0
                await progress.tick(True, job.key)
            except ContentPolicyBlocked as e:
                async with master_lock:
                    master[job.key] = {
                        "case_id": job.case_id,
                        "filename": job.filename,
                        "figure_number": job.figure_number,
                        "image_path": str(job.image_path.relative_to(REPO_ROOT)),
                        "source_caption": job.source_caption,
                        "description": None,
                        "error": "content_policy_violation",
                        "error_detail": str(e)[:500],
                        "model": model,
                        "generated_at": utc_now(),
                    }
                    _write_case_sidecar(master, job.case_id)
                    atomic_write_json(MASTER_OUT, master)
                await progress.tick(False, job.key, err="content_policy_violation")
            except Exception as e:  # noqa: BLE001 - isolate worker failures
                await progress.tick(False, job.key, err=f"{type(e).__name__}: {e}")
        finally:
            queue.task_done()


async def run_async(args: argparse.Namespace) -> int:
    load_env()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
    model = args.model or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") or "gpt-4o-1120"

    if not endpoint or not api_key:
        print("Missing AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY", file=sys.stderr)
        return 2

    library_captions = extract_library_captions()
    jobs = discover_jobs(
        case_filter=args.case,
        missing_captions_only=args.missing_captions_only,
        library_captions=library_captions,
    )

    master: dict[str, Any] = load_json(MASTER_OUT, {})
    if not args.force:
        before = len(jobs)
        jobs = [
            j
            for j in jobs
            if not _record_is_done(master.get(j.key), retry_errors=args.retry_errors)
        ]
        skipped = before - len(jobs)
        if skipped:
            print(
                f"Skipping {skipped} already-handled figures "
                "(use --force to redo, --retry-errors to retry failed)"
            )

    if args.limit is not None:
        jobs = jobs[: args.limit]

    print(f"Images root: {ALL_CASES}")
    print(f"Output:      {MASTER_OUT}")
    print(f"Model:       {model}")
    print(f"Workers:     {args.workers}")
    print(f"Detail:      {args.image_detail}")
    print(f"Jobs:        {len(jobs)}")

    if args.dry_run:
        for j in jobs[:20]:
            print(f"  {j.key}  caption={j.source_caption!r}")
        if len(jobs) > 20:
            print(f"  ... +{len(jobs) - 20} more")
        return 0

    if not jobs:
        print("Nothing to do.")
        return 0

    client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    queue: asyncio.Queue[FigureJob | None] = asyncio.Queue()
    for job in jobs:
        await queue.put(job)
    for _ in range(args.workers):
        await queue.put(None)

    progress = Progress(len(jobs))
    master_lock = asyncio.Lock()
    workers = [
        asyncio.create_task(
            worker(
                queue,
                client,
                model,
                master,
                master_lock,
                progress,
                write_every=args.flush_every,
                image_detail=args.image_detail,
            )
        )
        for _ in range(args.workers)
    ]
    await asyncio.gather(*workers)
    atomic_write_json(MASTER_OUT, master)
    await client.close()

    print(
        f"Done. wrote {MASTER_OUT} "
        f"({progress.ok} ok, {progress.failed} failed, {len(master)} total keys)"
    )
    return 0 if progress.failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=6, help="Concurrent Azure requests (default 6)")
    p.add_argument(
        "--model",
        default=None,
        help="Azure deployment name (default: AZURE_OPENAI_DEPLOYMENT_NAME or gpt-4o-1120)",
    )
    p.add_argument("--limit", type=int, default=None, help="Process at most N figures")
    p.add_argument("--case", default=None, help="Only this case id, e.g. Case_01002")
    p.add_argument(
        "--missing-captions-only",
        action="store_true",
        help="Skip figures that already have a usable Figure N. caption in library/case_text",
    )
    p.add_argument("--force", action="store_true", help="Re-describe even if already in output JSON")
    p.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retry keys that previously failed (e.g. content_policy_violation)",
    )
    p.add_argument(
        "--image-detail",
        choices=("high", "low", "auto"),
        default="high",
        help="Azure image detail setting (default high; low uses fewer tokens)",
    )
    p.add_argument("--dry-run", action="store_true", help="List jobs without calling Azure")
    p.add_argument(
        "--flush-every",
        type=int,
        default=5,
        help="Flush master JSON every N successful writes per worker batch (default 5)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run_async(args)))


if __name__ == "__main__":
    main()
