# Running docent.ID locally

This guide assumes you're starting from a clean machine — no Python packages, no Node/npm, nothing project-specific installed yet. You'll need two things running at once: a Python backend (FastAPI) and a React frontend (Vite), each in its own terminal tab.

Total time: ~15 minutes.

---

## 0. Prerequisites

You need two tools installed system-wide before touching this repo:

### Conda
If you don't already have conda (Miniconda or Anaconda), install Miniconda:
- macOS/Linux: https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html
- Verify it worked: `conda --version`

### Node.js (which includes npm)
The frontend needs Node 18+ (Node 20 LTS recommended).
- Download from https://nodejs.org (choose the LTS version), **or** if you already use conda for this too: `conda install -c conda-forge nodejs`
- Verify it worked: `node --version` and `npm --version`

You do **not** need Docker, Postgres, or any database installed locally — the app runs fully in a degraded-but-functional mode without one (details below).

---

## 1. Get the code

If you were handed a zip instead of a git clone, unzip it and `cd` into the folder. Otherwise:

```bash
git clone <repo-url>
cd microbiology-agent-tutor
```

Everything below assumes your terminal's current directory is the repo root (the folder containing `run.py`, `src/`, `frontend/`, etc).

---

## 2. Backend setup (Python / FastAPI)

### 2a. Create and activate a conda environment

```bash
conda create -n docent python=3.11 -y
conda activate docent
```

(`docent` is just a name — call it whatever you like, just remember it, since you'll run `conda activate <name>` every time you come back to this project.)

### 2b. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, FAISS, OpenAI/Anthropic SDKs, and everything else the backend needs. It'll take a couple of minutes — some packages (`faiss-cpu`, `pandas`, `scikit-learn`) are large.

### 2c. (Optional) Add API keys for LLM features

The chat, voice, and guideline-search features need an LLM API key. The app **starts and runs fine without this** — the case library, browsing, and UI all work with zero configuration. If you skip this step, you'll just see warnings in the terminal about missing credentials, which is expected and safe to ignore for now.

To enable the LLM-dependent features, create a file named `dot_env_microtutor.txt` in the repo root (same folder as `run.py`):

```
USE_AZURE_OPENAI=false
OPENAI_API_KEY=sk-...your-key-here...
PERSONAL_OPENAI_MODEL=gpt-4o-mini
MODEL_NAME=gpt-4o-mini
TEACHING_MODEL_NAME=gpt-4o-mini
```

(If you're using Azure OpenAI instead, set `USE_AZURE_OPENAI=true` and fill in `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_DEPLOYMENT_NAME` instead of the `OPENAI_API_KEY` lines.)

This file is gitignored — never commit it. Ask whoever runs the project for the actual key values if you don't have your own.

### 2d. Start the backend

```bash
python run.py
```

You should see:
```
🚀 Starting MicroTutor V4 on http://localhost:5001
📚 API docs: http://localhost:5001/api/docs
...
INFO:     Application startup complete.
```

A handful of warnings above that (missing credentials, no database connection) are expected if you skipped step 2c or don't have a Postgres database configured — the app automatically falls back to file-based logging and disables the affected features. As long as you see `Application startup complete.` at the end, it worked.

**Leave this terminal running.** Open a new terminal tab/window for the next part.

**Quick check:** visit http://localhost:5001/api/docs in a browser — you should see the interactive API docs (Swagger UI).

---

## 3. Frontend setup (React / Vite)

In your **new terminal tab** (conda env not needed here — this is all Node/npm):

```bash
cd microbiology-agent-tutor/frontend   # adjust path as needed
npm install
npm run dev
```

You should see:
```
VITE vX.X.X  ready in ### ms
➜  Local:   http://localhost:5173/
```

Open that URL in a browser. You should see the docent.ID login screen. Log in with `admin` / `admin` (hardcoded for now).

---

## 4. Sanity checks

With both servers running:

- **Case library** — click "Case library" in the app; you should see ~592 real cases with images. This works with zero API keys.
- **Pathogen dropdown** — on the setup screen, the organism search should show over 100 organisms grouped by Bacteria/Viruses/Fungi/Parasites.
- **Chat / tutoring** — starting an actual case requires the API key from step 2c. Without it, you'll get an error when trying to start a case — that's expected.

---

## Troubleshooting

**`Address already in use` when starting the backend**
Something is already listening on port 5001 (probably a backend process you forgot to stop).
```bash
lsof -i :5001        # find the PID
kill -9 <PID>
python run.py         # retry
```
Or just run on a different port: `PORT=5002 python run.py` (and use that port in the URLs above).

**Vite says "Port 5173 is in use, trying another one..." and picks 5174 (or another port)**
Harmless — just use whatever port it reports instead of 5173. Everything (including the API proxy) still works.

**`npm install` prints a warning about `fsevents` / `allow-scripts`**
Harmless, macOS-specific, unrelated to this project. Ignore it, or run `npm approve-scripts --allow-scripts-pending` if it bothers you.

**Backend logs a `psycopg2.OperationalError` about a database host**
Expected if you don't have the production Postgres database configured. The app catches this and falls back to file-based logging automatically — this is not a failure, just noise. Everything else still works.

**Case library loads but individual cases are empty, or images are broken**
Make sure you're running the latest code — this was a known issue that's since been fixed (the frontend now fetches full case detail and images through the backend automatically; no manual file copying required).

**Frontend can't reach the backend (`/api/...` requests fail or return the wrong thing)**
Make sure the backend (step 2d) is actually running on port 5001 before starting the frontend. The frontend dev server proxies API calls to `http://localhost:5001` — if nothing's there, those calls fail.

---

## Day-to-day (after initial setup)

Once everything above is done once, starting the app again next time is just:

```bash
# terminal 1
conda activate docent
python run.py

# terminal 2
cd frontend
npm run dev
```

No need to redo `pip install` or `npm install` unless `requirements.txt` or `package.json` changed since you last pulled.
