GuitarWiring

An interactive web application for analyzing and visualizing humbucker pickup wiring configurations. Built with Streamlit and integrated with Ollama for AI-assisted guidance.

 Recovery Point
If you need to revert to the last stable version, use:

```bash
git checkout stable-v1
```

Features
- Interactive Pickup Analysis: Measure and analyze humbucker pickup wire configurations
- Visual Diagrams: Generate SVG diagrams showing coil orientations and wire connections
- AI Assistant: Get guidance on pickup installation using local Ollama LLM
- Manufacturer Presets: Pre-configured color schemes for major pickup manufacturers
- Modular Architecture: Step-based workflow for intuitive user experience
- Reliable State Management: Persistent user inputs without constant page refreshes

Prerequisites
- Python 3.12 or higher
- Ollama installed locally (optional, for AI features)

Installation
Clone the repository:

```bash
git clone https://github.com/JKeskinen/GuitarWiring.git
cd GuitarWiring
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Install dependencies:

```powershell
.venv\Scripts\pip.exe install -r app\requirements.txt
```

Usage
Run the application using the startup script:

```powershell
python start_web.py
```

This will:
- Start the Ollama server (in a separate window)
- Launch the Streamlit web application at http://localhost:8501

Alternatively, run Streamlit directly:

```powershell
.venv\Scripts\python.exe -m streamlit run app/main.py
```

Configuration
Ollama Settings
Set environment variables to customize the AI backend:

- LLM_BACKEND: Set to "ollama" to enable AI features (default)
- OLLAMA_URL: Ollama server URL (default: http://127.0.0.1:11434)
- OLLAMA_MODEL: Model to use (default: mistral)

Example:

```powershell
set OLLAMA_MODEL=llama2
python start_web.py
```

Project Structure
```
GuitarWiring/
 app/
    main.py              # Main Streamlit application
    wiring.py            # Pickup wiring logic and SVG generation
    humbucker.py         # Humbucker visualization
    logic.py             # Analysis and calculation logic
    llm_client.py        # Ollama client for AI features
    steps/               # Modular step components
       step_measurements.py
       step_wiring_mode.py
       step_pole_assignment.py
       step_switch_config.py
       step_soldering_instructions.py
       step_summary.py
    requirements.txt     # Python dependencies
 start_web.py             # Application launcher
 README.md
```

Dependencies
- streamlit>=1.20.0 - Web framework
- requests>=2.28.0 - HTTP client for Ollama API

License
This project is open source and available for educational purposes.

AI Integration
--------------

The app optionally integrates with a local Ollama-compatible LLM to provide contextual guidance, explanations, and troubleshooting. Key details:

- Backend selection: set `LLM_BACKEND` to `ollama` to enable AI features; the app falls back to an offline FAQ when no AI backend is reachable.
- Connection settings: customize with `OLLAMA_URL` (default `http://127.0.0.1:11434`) and `OLLAMA_MODEL` (set to the exact model id reported by your server, e.g. `mistral:7b`).
- Prompt construction: prompts include the user question, current step (1..6), detected `neck_colors` and `bridge_colors` if available, `wiring_mode`, and an instruction block that enforces the "engineer-turned-guitarist" persona (concise, safety-first, no nautical/pirate or stage-nickname metaphors).
- Local shortcuts: queries that match "I'm on step N" are answered instantly from local `step_guides` without calling the LLM to ensure deterministic, concise guidance for graders or offline demos.
- Streaming & fallback behavior: the app first checks model health, then streams responses from the generation endpoint for interactive display. If streaming fails but the health-check reports the server as reachable, the app will attempt a synchronous generate call so the user still receives AI-generated text. Only when the server is unreachable does the app use the offline FAQ.
- Embeddings probe: the `app/llm_client.py::SimpleLLM.embeddings()` helper can query common embeddings endpoints; results depend on the `OLLAMA_MODEL` and server implementation.
- Logging: AI prompts and responses are appended at runtime to `app/ai_input_log.jsonl` for audit and debugging. If you prefer not to keep these logs, add `app/ai_input_log.jsonl` to `.gitignore` (or remove the file before committing).

Security & privacy note: the app is designed to work with a local LLM server. Do not point `OLLAMA_URL` to an external or untrusted service if you will be sending sensitive information.
