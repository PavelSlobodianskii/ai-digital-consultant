# AI Digital Consultant

Local MVP: describe a business process, get a **9-section** automation assessment, and store **feedback lessons** in SQLite. A deterministic rubric decides **rules vs AI vs hybrid**. Retrieved lessons inform later cases; they do **not** retrain a model.

No cloud APIs. No paid services.

## What you need on Windows

1. **Python 3.11 or newer** — [https://www.python.org/downloads/](https://www.python.org/downloads/)  
   During setup, check **Add python.exe to PATH**.
2. **Ollama** — [https://ollama.com/download](https://ollama.com/download)  
   Install, then confirm it is running (the Ollama app in the system tray, or the service).
3. A local model. Default in this project:

```powershell
ollama pull llama3.1:8b
```

If that is too slow or too large for your machine:

```powershell
ollama pull llama3.2:3b
```

Then set `OLLAMA_MODEL=llama3.2:3b` before starting the app (see below).

Optional check:

```powershell
python --version
ollama list
```

## Setup (once)

In PowerShell, from this folder (`AI-Digital-Consultant`):

```powershell
cd C:\Users\Slobodianski\AI-Digital-Consultant
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If execution policy blocks the venv script, the `Set-ExecutionPolicy` line is only for the current PowerShell window.

Copy environment defaults (optional):

```powershell
copy .env.example .env
```

The app reads `OLLAMA_HOST`, `OLLAMA_MODEL`, and `CONSULTANT_DB` from the **process environment**. A `.env` file is documentation unless you export those variables yourself.

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "llama3.1:8b"
```

## Run tests (no Ollama required)

```powershell
cd C:\Users\Slobodianski\AI-Digital-Consultant
.\.venv\Scripts\Activate.ps1
python -m pytest
```

You should see tests for the rubric and for memory retrieval pass.

## Run the app

Keep Ollama running, then:

```powershell
cd C:\Users\Slobodianski\AI-Digital-Consultant
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

1. Click a sample process (or paste your own).
2. Run assessment (first CPU run can take a minute).
3. After you try a recommendation in real life, submit **Worked / Partially worked / Did not work** so similar future cases can retrieve that lesson.

SQLite file: `data\consultant.db` (created automatically).

## How memory works

- Feedback is stored locally. The LLM **never** writes the lessons table.
- New assessments retrieve up to **3** similar usable lessons using tag + keyword overlap.
- **Relevance** does not use the outcome (worked vs failed).
- **Quality** (`quality_status`, `weight`) decides whether a lesson is eligible.
- Outcomes are shown to the model as evidence. One failure is not treated as a universal ban.
- If retrieved successes and failures disagree, the UI says so.
- A **clear** rubric result is not overridden by memory or by the model.

## Project layout

```
app/           API, rubric, memory, LLM client, UI
data/          SQLite database (runtime)
tests/         Rubric and retrieval tests
```
