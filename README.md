# Humbucker Solver

Status: Finalized for course submission. This README documents how to run the app, how local AI is used, and where to find the core code.

What this project is
--------------------
A Streamlit application that guides you through identifying pickup wires, testing pickup phase, and producing a wiring analysis for two humbucker pickups. It includes an optional local LLM assistant used for explanations, step guidance, and brief troubleshooting.

Web app overview
----------------
Purpose: This web app is designed to help guitar hobbyists, technicians, and students systematically identify pickup wire colors, determine coil polarity/phase, and assemble a correct wiring configuration for humbucker pickups. It reduces guesswork by providing step-by-step UI flows, automated checks, and clear soldering instructions.

What it does (features):
- Interactive page-per-step workflow: Walks users through Welcome → Wire color selection → Polarity checks → Measurements → Probe/phase checks → Final analysis.
- Wire-to-coil mapping: Let users map detected wire colors to the pickup's coils (upper/lower), then validate selections.
- Phase & probe guidance: Guides the user to touch pole pieces and record resistance changes to determine START/FINISH and electrical phase.
- Soldering instructions & safety tips: Provides concise, practical soldering steps and safety reminders in Step 5.
- AI assistant sidebar: Optional local LLM provides expanded explanations, troubleshooting, and contextual help; short local step guidance is returned instantly for "I'm on step N" queries.
- Logging & audit: All AI interactions are appended to `app/ai_input_log.jsonl` for review and debugging. The sidebar includes a log viewer and an embeddings probe.

Intended users and workflow:
- Target users: hobbyists replacing or modifying pickups, guitar technicians verifying hum-cancellation, and students learning pickup wiring.
- Typical workflow: Open the app → define wire colors → perform polarity checks with a multimeter → map probe results → review generated wiring analysis → follow soldering instructions → test.

Inputs and outputs:
- Inputs: color selections, multimeter resistance values, probe mapping selections, wiring mode choice.
- Outputs: wiring analysis, recommended connections for pots/switches, step-by-step soldering guidance, and AI explanations when requested.

Limitations and assumptions:
- The app assumes basic user familiarity with a multimeter and safe soldering practices.
- AI explanations require a local Ollama-compatible server; without it, the app uses a built-in offline FAQ.
- The tool focuses on humbucker-style dual-coil pickups and typical wiring scenarios; highly custom wiring may require manual adaptation.

Quick start (PowerShell)
------------------------
1) Create and activate a venv:

```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
```

2) Install dependencies:

```powershell
pip install -r app/requirements.txt
```

3) (Optional) Configure local LLM if you want AI responses:

```powershell
$env:OLLAMA_URL = 'http://127.0.0.1:11434'    # default
$env:OLLAMA_MODEL = 'mistral:7b'             # set to the exact model id your server reports
```

4) Start the app:

```powershell
# preferred launcher
python start_web.py

# or directly with Streamlit
python -m streamlit run app/main.py --server.port 8501
```

How the local AI is used
------------------------
- The app talks to a local Ollama-like HTTP server by default (controlled by `OLLAMA_URL` and `OLLAMA_MODEL`).
- Behavior summary:
  - On sidebar questions, the app builds a context prompt that includes the user question, the current step, and optional pickup state (neck/bridge coil colors, wiring mode).
  - If the question matches a local shortcut like "I'm on step N", the app returns a concise local `step_guides[N]` text without calling the LLM.
  - If the LLM server is reachable, the app streams a response from `/api/generate` for interactive display. If streaming fails but the server health-check is OK, the app will attempt a synchronous generate call so the user still receives AI-generated text.
  - If the server is not reachable, the app falls back to a small offline FAQ so the user still receives practical guidance.
  - Responses (prompt + response + metadata) are appended to `app/ai_input_log.jsonl` for audit and debugging.

Prompt construction (high-level)
--------------------------------
- Prompts are assembled in `app/ai_assistant.py::build_context_prompt()` and include:
  - The user question
  - Current step (1..6)
  - `neck_colors` and `bridge_colors` if available
  - `wiring_mode` if set
  - An instruction block that sets the assistant persona: an "engineer-turned-guitarist" who gives concise, safety-first, practical instructions and avoids certain banned language (no nautical/pirate wording, no stage-nickname metaphors).
- The assistant also contains a small `easter_eggs` map that returns canned replies for certain playful triggers.

Files and responsibilities
--------------------------
- `start_web.py` — small launcher that runs the app from repo root.
- `app/main.py` — Streamlit UI, page-per-step flow, compact-mode CSS, state backup, and wiring analysis UI.
- `app/ai_assistant.py` — AI sidebar wrapper: health-check, `build_context_prompt()`, streaming logic, local `step_guides`, JSONL logging, and regeneration logic when responses contain banned casual phrasing.
- `app/llm_client.py` — `SimpleLLM` HTTP helper used for generation and embeddings.
- `app/wiring.py`, `app/logic.py` — domain logic: compute wiring order, polarity, and analysis helpers.
- `app/humbucker.py` — pickup data structures and helpers.
- `app/steps/` — per-step helpers (measurements, pole assignment, soldering instructions, summary, etc.).
- `app/_run_ai_query.py` — small helper script to exercise the assistant from the CLI.
- `app/ai_input_log.jsonl` — local append-only log of prompts and responses (created at runtime).

Notes about prompts, safety, and tone
------------------------------------
- The app attempts to enforce a consistent tone by:
  - Including a persona/instruction block in the prompt
  - Checking LLM responses for banned words (nicknames, pirate phrases). If found, the app will ask the model to regenerate with a stricter prompt.
  - Returning local step guidance for explicit "I'm on step N" queries to guarantee concise, non-generic answers.

Embedding support
-----------------
- You can compute embeddings for recorded responses via `app/llm_client.py::SimpleLLM.embeddings()`; endpoints vary by server implementation and the `OLLAMA_MODEL` value must match the server.

Troubleshooting
---------------
- If AI responses are missing or empty: check that `OLLAMA_URL` is correct and the model specified in `OLLAMA_MODEL` is installed on the server.
- If embeddings return 404: ensure your model id matches the server listing (e.g., `mistral:7b`).
- To replay or debug an assistant interaction, run `python app/_run_ai_query.py`.


```powershell
git add .
git commit -m "chore: finalize project for submission — README and UI"
git checkout -b release/course-final
git push -u origin release/course-final
```





