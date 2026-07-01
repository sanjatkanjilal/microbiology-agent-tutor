# docent.ID — MicroTutor

An AI-powered microbiology tutoring system: an LLM-driven clinical case tutor (chat, voice, guideline search) paired with a browsable library of 592 real MGH ID Images teaching cases.

**→ First time here? Start with [SETUP.md](SETUP.md) for step-by-step local setup, assuming a clean machine.**

This document covers what the project *is* and what's changed recently. For "how do I run this," see SETUP.md instead.

---

## Repository structure

```
.
├── config/            # App configuration (env loading, settings)
├── data/              # Case library, guidelines, feedback indices, DB
│   └── cases/
│       ├── case_library.json      # 592 cases — title, history, exam, diagnosis, figures
│       ├── organisms.json         # Curated pathogen list, derived from case diagnoses
│       └── ID_Images/All_cases/   # ~2,100 case figure JPGs
├── frontend/          # React (Vite) single-page app
├── scripts/           # One-off/maintenance scripts (image scraping, organism extraction, etc.)
├── src/microtutor/    # Main Python package — API, services, tools, schemas, prompts
├── run.py / start.sh  # Backend entry points
├── render.yaml        # Render.com deployment config
└── SETUP.md           # Local setup guide
```

---

## Recent history

### Repo restructuring (V1–V4 → single tree)

This project went through four iterations of the backend (`V1_multiagent`, `V2_reasoning_model`, `V3_reasoning_multiagent`, `V4_refactor`), living side by side in the repo. That's been cleaned up:

- **`V1_multiagent/`, `V2_reasoning_model/`, `V3_reasoning_multiagent/` were deleted.** Before removing them, every file was checked for dependencies on the old folders — the only real one was a dead fallback in `dependencies.py` that pulled config from `V3_reasoning_multiagent` if the V4 config import failed (it never actually fired, since the V4 config always resolves). That fallback was removed.
- **`V4_refactor/`'s contents were promoted to the repo root.** Everything that used to live at `V4_refactor/src/...`, `V4_refactor/frontend/...`, etc. is now at `src/...`, `frontend/...` directly. Path-resolution code that walks up from `__file__` to the project root (`.parent.parent...` chains) didn't need to change — those files were already the same number of directories away from the root, just under a different root name.
- **`src_simplified/`** (an older, parallel backend implementation) **was removed.** `src/microtutor/` — the full FastAPI package that the current React frontend actually talks to — is the one and only backend going forward. `render.yaml`'s deploy command was updated to match (`start.sh` instead of the now-deleted `run_simplified.sh`).
- **A stray, broken duplicate frontend scaffold** (a second `App.jsx`/`main.jsx`/`vite.config.js` accidentally committed at the old `V4_refactor/` top level, separate from the real `frontend/` app) was removed. Its `vite.config.js` did contain one piece of logic that mattered — the dev-server API proxy — which was merged into the real `frontend/vite.config.js` before the duplicate was deleted.
- A couple of latent bugs surfaced and were fixed while verifying the restructuring didn't break anything: an off-by-one directory-depth bug in `app.py`'s case-images static mount, and a hardcoded personal-machine path in a dev-only script (`processor.py`).

### Frontend fixes

- **Case library pagination bug.** The frontend requested `/api/v1/cases?limit=600`, but the backend capped `limit` at 592 (the exact case count) — the mismatch caused a validation error that was silently swallowed as an empty list. Backend cap raised to 1000.
- **Pathogen dropdown expanded from 18 → 118 organisms.** The old dropdown was a small hardcoded array. The new list is derived from the actual 592 case diagnoses (extracted, deduplicated, and grouped into Bacteria/Viruses/Fungi/Parasites) — see `data/cases/organisms.json` and `scripts/extract_organism_candidates.py` if you need to regenerate it after adding cases. The frontend loads this at runtime from `/organisms.json`, with the original small list kept as an in-code fallback if that fetch fails.
- **Case detail pages were rendering empty, with broken images.** Root cause: the frontend's case-list cache (used for both the library list *and* individual case detail pages) only has full text (`history`/`exam_studies`/`diagnosis`/`more_info`) when `frontend/public/case_library.json` has been manually copied in (see "Static data files" below) — otherwise it silently falls back to a summary-only API response. Detail pages now detect the summary-only case and fetch the full record from `/api/v1/cases/{id}` instead. Separately, the Vite dev server was only proxying `/api/*` to the backend, not `/case-images/*` — so images 404'd in dev even though the backend was serving them correctly. Both are now proxied, which also means **the manual `case-images/` copy step is no longer required for local development.**

---

## Frontend overview

A React 19 + Vite single-page app. All styling uses inline CSS variables (no external CSS framework), with full light/dark mode.

**Pages and features:**
- **Login** — username/password (hardcoded `admin`/`admin` for now; replace with real auth)
- **Setup screen** — type-ahead organism search (118 organisms, grouped by kingdom), module selection (History Taking, Differential Diagnosis, Management, Pathophys & Epidemiology)
- **Chat screen** — 3-column layout: Case Summary + Curbside Consult | Chat | Electronic Medical Record
  - Per-module progress bars, module switching mid-case
  - Random case mode with organism name hidden until revealed
  - Curbside Consult hits `/api/v1/clarify` for quick questions without disrupting the case
- **Case Library** — all 592 scraped MGH ID Images cases, searchable by title/history/diagnosis
  - Sticky search bar, sticky column headers
  - Click any row to open a tabbed case detail page (History, Exam/Studies, Diagnosis, More Info, Single Page)
  - Collapsible figure images inline with text
  - Works with **no API key required** — text and images are served by the backend directly (or from static files, if you've copied them in — see below)
- **About** pages — Overview, Architecture, The Team (content TBD)
- **How it works** modal

### Backend surface the frontend depends on

| File | Purpose |
|------|---------|
| `src/microtutor/api/app.py` | Registers the `cases` router; mounts `/case-images` as static files |
| `src/microtutor/api/routes/cases.py` | Serves case data via `/api/v1/cases` (summary list) and `/api/v1/cases/{id}` (full record) |
| `src/microtutor/services/case/case_loader.py` | Wraps `CaseGeneratorRAGAgent()` in try/except so the server starts fine without API credentials |

### Static data files (optional, for local dev)

| File | Canonical location | Frontend copy (optional) |
|------|------|------|
| `case_library.json` | `data/cases/` | `frontend/public/case_library.json` |
| `organisms.json` | `data/cases/` | `frontend/public/organisms.json` |
| Case images (~2,100 JPGs) | `data/cases/ID_Images/All_cases/` | `frontend/public/case-images/` |

None of these copies are required anymore — the frontend falls back to the backend's API for all of them during local dev (see "Case detail pages" fix above). Copying them into `frontend/public/` is only worth doing if you want the Case Library to work with the backend turned off entirely (e.g. static hosting, or a deploy setup where the frontend and API are served from different origins).

`case_library.json`'s schema, per case:

```json
{
  "id": "Case_01001",
  "title": "An HIV-positive male with fever, cough, and skin lesions.",
  "history": "...",
  "exam_studies": "...",
  "diagnosis": "...",
  "more_info": "...",
  "figures": ["figure1.jpg", "figure2.jpg"],
  "tags": []
}
```

The `tags` field is intentionally empty — see **Adding tags** below.

---

## Running locally

See **[SETUP.md](SETUP.md)** for the full walkthrough (installing conda/Node, environment setup, starting both servers, troubleshooting). Short version once everything's installed:

```bash
# terminal 1 — backend
conda activate docent
python run.py

# terminal 2 — frontend
cd frontend
npm run dev
```

Backend: http://localhost:5001 (docs at `/api/docs`). Frontend: http://localhost:5173.

### Connecting the LLM (OpenAI / Azure OpenAI)

Create a file called `dot_env_microtutor.txt` in the repo root — gitignored, never commit it.

**Standard OpenAI:**
```
USE_AZURE_OPENAI=false
OPENAI_API_KEY=sk-...
```

**Azure OpenAI:**
```
USE_AZURE_OPENAI=true
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

Restart the backend after creating this file. The chat screen will then be fully functional. Everything else (case library, pathogen search) works without it.

---

## Adding tags to cases (for the NLP team)

The `case_library.json` has a `tags` field (currently `[]`) on every case. Tags will be used to:

1. Filter the Case Library by organism, infectious syndrome, and host characteristics
2. Power richer organism search on the Setup screen beyond the current curated `organisms.json` list

### Tag schema

Tags are stored as a flat array of prefixed strings:

```json
"tags": [
  "organism:Staphylococcus aureus",
  "syndrome:skin and soft tissue infection",
  "host:immunocompetent adult",
  "host:healthcare worker"
]
```

Using a `type:value` prefix keeps tags queryable without needing a separate schema. Multiple tags of the same type are allowed.

### Workflow

1. Run your NLP tagging pipeline against `data/cases/case_library.json`
2. Populate the `tags` array for each case and save
3. Copy the updated file to the frontend public folder:
   ```bash
   cp data/cases/case_library.json frontend/public/case_library.json
   ```
4. The frontend picks up the new tags on next page load — no code changes needed until the filter UI is wired up

### Suggested NLP approach

- **Organism tags** — extract from the `diagnosis` field (contains Final Diagnosis + Discussion); the organism name is almost always in the first sentence. `scripts/extract_organism_candidates.py` already does a first pass of this (regex + keyword matching) to help seed `organisms.json` — the same approach extends to per-case tagging.
- **Syndrome tags** — extract from `diagnosis` and `title`; look for the clinical presentation pattern
- **Host tags** — extract from `history`; look for age descriptors, comorbidities, immunosuppression, travel, occupation, exposures

A few-shot GPT extraction prompt on these fields works well given the highly structured nature of the MGH case text.

---

## Building for production

```bash
cd frontend
npm run build
```

Compiles the React app into `src/microtutor/api/static/react/`. FastAPI serves it at the root URL when deployed to Render.

---

## Project status

| Feature | Status |
|---------|--------|
| React frontend | ✅ Complete |
| Case library — 592 MGH cases, all figures | ✅ Complete |
| Pathogen dropdown — 118 organisms from real case data | ✅ Complete |
| Chat screen — 3-column layout, module tabs | ✅ Complete |
| Curbside consult | ✅ Complete |
| Light / dark mode | ✅ Complete |
| Random case (organism hidden) | ✅ Complete |
| About / How it works / Case library pages | ✅ Complete |
| Repo restructuring (V1–V4 → single tree) | ✅ Complete |
| LLM chat (start_case, chat) | ⏳ Requires API key |
| Case tags and library filters | ⏳ NLP tagging pending |
| My history page | ⏳ Requires backend session tracking |
| About — team bios and architecture docs | ⏳ Content TBD |
| Real authentication | ⏳ Hardcoded admin/admin for now |
