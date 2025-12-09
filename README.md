# GuitarWiring

An interactive web application for analyzing and visualizing humbucker pickup wiring configurations. Built with Streamlit and integrated with Ollama for AI-assisted guidance.

## Features

- **Interactive Pickup Analysis**: Measure and analyze humbucker pickup wire configurations
- **Visual Diagrams**: Generate SVG diagrams showing coil orientations and wire connections
- **AI Assistant**: Get guidance on pickup installation using local Ollama LLM
- **Manufacturer Presets**: Pre-configured color schemes for major pickup manufacturers
- **Modular Architecture**: Step-based workflow for intuitive user experience
- **Reliable State Management**: Persistent user inputs without constant page refreshes

## Prerequisites

- Python 3.12 or higher
- [Ollama](https://ollama.ai/) installed locally (optional, for AI features)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/JKeskinen/GuitarWiring.git
cd GuitarWiring
```

2. Create a virtual environment:
```bash
python -m venv .venv
```

3. Install dependencies:
```bash
.venv\Scripts\pip.exe install -r app\requirements.txt
```

## Usage

Run the application using the startup script:

```bash
python start_web.py
```

This will:
1. Start the Ollama server (in a separate window)
2. Launch the Streamlit web application at http://localhost:8501

Alternatively, run Streamlit directly:

```bash
.venv\Scripts\python.exe -m streamlit run app/main.py
```

## Configuration

### Ollama Settings

Set environment variables to customize the AI backend:

- `LLM_BACKEND`: Set to "ollama" to enable AI features (default)
- `OLLAMA_URL`: Ollama server URL (default: http://127.0.0.1:11434)
- `OLLAMA_MODEL`: Model to use (default: mistral)

Example:
```bash
set OLLAMA_MODEL=llama2
python start_web.py
```

## Project Structure

```
GuitarWiring/
├── app/
│   ├── main.py              # Main Streamlit application
│   ├── wiring.py            # Pickup wiring logic and SVG generation
│   ├── humbucker.py         # Humbucker visualization
│   ├── logic.py             # Analysis and calculation logic
│   ├── llm_client.py        # Ollama client for AI features
│   ├── steps/               # Modular step components
│   │   ├── step_measurements.py
│   │   ├── step_wiring_mode.py
│   │   ├── step_pole_assignment.py
│   │   ├── step_switch_config.py
│   │   ├── step_soldering_instructions.py
│   │   └── step_summary.py
│   └── requirements.txt     # Python dependencies
├── start_web.py             # Application launcher
└── README.md
```

## Dependencies

- `streamlit>=1.20.0` - Web framework
- `requests>=2.28.0` - HTTP client for Ollama API

## License

This project is open source and available for educational purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
