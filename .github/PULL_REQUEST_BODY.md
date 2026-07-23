## Summary

Upgrade DocentID session pipeline from heuristic EMR + soft-routed chat into bound case packages, structured EMR extraction, capacity-aware encounter voice, module hard-routing with an explicit Ask Docent path, and LLM figure reveal.

Branch tip is shared by `feature/patient-first-person-opening` and `feature/emr-summaries-and-ui-fixes`.

---

## Before → after (by subsystem)

### 1. EMR / chart panel

| | Before | After |
|---|--------|--------|
| **Mechanism** | Chart updates tied to chat-path / heuristic summarization of dialogue | Backend structured LLM extraction (`services/emr/`) **enqueued asynchronously** after the patient/Ix reply; `/chat` returns immediately with `emr_busy`; frontend polls `/emr_notes` until fields land |
| **Strength retained** | Students still see a running bedside chart during the case | Same panel role; richer structured `emr_notes` / `emr_data` |
| **Limitation addressed (latency)** | Doing chart LLM work on the critical path would add another model round-trip before the student sees the clinical reply | EMR extraction runs in the background; chat latency stays dominated by the encounter agent only |
| **Limitation addressed (structure)** | Heuristic grouping had no server-side field schema | Typed extraction from patient/investigation exchanges; busy + refresh APIs for incomplete/re-run jobs |
| **UI** | Multi-line EMR text rendering was inconsistent | Bullet formatting for multi-line EMR summaries |

### 2. Case narrative ↔ figures binding

| | Before | After |
|---|--------|--------|
| **Mechanism** | Organism-keyed case text and case-library figures could be resolved independently | `CasePackage` binds narrative + `library_case_id` + figures (+ figure catalog) for the session |
| **Strength retained** | Library cases and organism cache/RAG still available | Same sources; resolution prefers figure-bearing library matches when starting by organism |
| **Limitation addressed** | Patient agent could answer from one narrative while the UI showed figures from another library entry | One package per session; optional explicit `library_case_id` start |

### 3. Message routing (History module) — latency is the core issue

| | Before | After |
|---|--------|--------|
| **Mechanism** | Tutor LLM soft-routed tools on every routine turn, then the chosen agent ran (typically patient) | Hybrid: `active_module` hard-routes (`history_taking` → patient tool directly); optional `route_to: "tutor"` only when the student selects Ask Docent |
| **Strength retained** | Phase-skip / “Let’s move onto phase:…” path kept; coach still available when requested | Same transition/summary path; Ask Docent is an explicit send-target, not a silent classifier |
| **Limitation addressed (latency)** | **Two serial LLM hops** on routine HPI/exam/Ix (tutor router → patient), so History replies paid router latency even when the UI module already selected History | One LLM hop for default History Send (`tools_used: ["patient"]`) |
| **Limitation addressed (control)** | Soft-router could disagree with the selected UI module; waiting UI defaulted assistant bubbles to Docent | UI module is source of truth; loading bubble has no speaker/avatar until the reply arrives |

**Consequence of going direct to the patient agent:** the patient tool must cover all History-module utterances (verbal history, collateral, and clinical reporting). That motivates speaker markers and the separate Docent channel below—not a second router LLM.

### 4. Encounter voice / openings (follows from direct patient routing)

| | Before | After |
|---|--------|--------|
| **Mechanism** | Docent opened the case by **introducing the patient in third person** (tutor vignette); subsequent replies used one undifferentiated patient voice | Fixed short Docent frame, then the **case side introduces itself**: LLM greeting/replies emit `[[speaker:patient\|family\|nurse]]` (patient 1st person when able; named family/nurse proxy when not) |
| **Strength retained** | Clear case kickoff before history-taking | Still a Docent frame, then an in-world opening line |
| **Limitation addressed** | Third-person Docent intro kept the student outside the encounter; a single patient voice is also wrong for sedated/intubated packages and for exam/obs/Ix once History is hard-routed to the patient agent | Case text selects capacity each turn: **patient** (1st person), **family** (collateral), **nurse** (3rd-person clinical / proxy historian). Exam/obs/Ix → `[[speaker:nurse]]` |
| **Docent separation** | Docent both framed the case and sat in the soft-router path for routine turns | Docent frame stays one-time; coaching only via Ask Docent (`route_to: "tutor"`); case voice stays on the module agent |

### 5. Figure reveal + description catalog

| | Before | After |
|---|--------|--------|
| **Mechanism** | Frontend keyword heuristics unlocked images; figure metadata was thin (often short library captions / placeholders) | (1) Master JSON `data/cases/figure_descriptions.json` stores a **per-figure** record (case id, filename, number, source caption, vision `description`, model/error); (2) session figure catalog injects those descriptions into the patient prompt; (3) patient emits `[[display_figure:N]]`; backend returns `revealed_figures` |
| **Strength retained** | Figures still shown in the case image panel | Same panel; unlock is now request-driven rather than keyword-driven |
| **Limitation addressed (hit rate)** | Short/placeholder captions gave the model little to match against (“Physical finding”, “See text”), so appropriate figures were under-shown or poorly timed | Batch vision script (`scripts/describe_case_figures.py`) writes **extensive, explicit clinical descriptions** per image into the JSON (~2046 ok; ~101 `content_policy_violation` kept with error fields). Richer descriptions raise the rate at which the correct figure is shown when the student asks for the matching exam/imaging/lab finding |
| **Limitation addressed (control)** | Keyword unlock could diverge from bound case figures | Catalog is built from the session `CasePackage` figure list + JSON descriptions; only listed `N` values are valid |

### 6. Repo hygiene

| | Before | After |
|---|--------|--------|
| **Tracked local artefacts** | `data/microtutor.db`, `case_cache.json` could churn in git status | Ignored + removed from the index |
| **Secrets / logs** | `dot_env_microtutor.txt` ignore pattern broken by inline `#` comment; `logs/` not ignored as a directory | Fixed ignore rules for env file, `logs/`, DB, and case cache |

---

## Dependency order (how pieces connect)

```
Latency: tutor soft-router + agent (2 LLM hops)
        ↓
Hard-route History → patient (1 hop)
        ↓
┌──────────────────────────────────────────────┐
│ Patient tool must own all History utterances │
│  → [[speaker:patient|family|nurse]]          │
│  → Ask Docent as separate send target         │
└──────────────────────────────────────────────┘

Parallel latency track:
Chat reply (critical path) ⟂ async EMR LLM enqueue + poll

CasePackage binds narrative + figures for both voice and figure reveal
        ↓
[[display_figure:N]] + caption catalog
```

Hard-routing is motivated by **response latency** (drop the router hop). Voices + Ask Docent follow because the patient agent becomes the sole History recipient. EMR uses the same latency principle: keep chart LLM work **off** the chat critical path via async enqueue/poll. Case binding keeps narrative/figures consistent for voice and reveal.

Ask Docent coaches from conversation-revealed facts + private case context (≤2 paragraphs; no spoilers unless explicitly requested). Textbook retrieval is out of scope for this PR.

---

## Key files

| Area | Paths |
|------|--------|
| EMR | `src/microtutor/services/emr/`, `src/microtutor/prompts/emr_prompts.py` |
| Case binding | `src/microtutor/services/case/case_package.py` |
| Voice | `src/microtutor/prompts/patient_prompts.py`, `src/microtutor/services/case/speaker_markers.py` |
| Routing | `src/microtutor/services/tutor/service.py`, `src/microtutor/utils/module_routing.py` |
| Figures | `src/microtutor/services/case/figure_catalog.py`, `scripts/describe_case_figures.py`, `data/cases/figure_descriptions.json` |
| UI | `frontend/src/DocentID.jsx` |
| API contracts | `src/microtutor/schemas/api/requests.py`, `responses.py`, `api/routes/chat.py` |

---

## Test plan

- [ ] Ambulatory library case: `speaker=patient` greeting; first-person HPI.
- [ ] ICU sedated/intubated library case: `speaker=family` or `nurse` named opener; no first-person ambulatory greeting.
- [ ] History default Send: `tools_used` includes `patient` (hard route); speaker label matches marker.
- [ ] Obs/exam/Ix: `speaker=nurse`; figure numbers in `revealed_figures` when catalog matches.
- [ ] Ask Docent approach question: ≤2 paragraphs; no organism name unless explicitly requested; helpful process coaching without textbook citations; send target resets to module.
- [ ] EMR fields update after patient/test turns; busy/refresh behave; bullets render.
- [ ] Module tab change sends updated `active_module` on next chat.
- [ ] Diff excludes `dot_env_microtutor.txt`, `logs/`, and local `microtutor.db`.
