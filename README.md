# AI Guitar Humbucker Assistant

This project is a course work for the course "Utilizing Generative AI" (Finnish: "Generatiivisen tekoälyn hyödyntäminen"). It is an interactive assistant for designing, configuring, and understanding guitar humbucker pickups using AI-powered logic and step-by-step guidance.

## Overview

The application helps users:
- Design and configure custom humbucker pickups
- Understand wiring modes and switch configurations
- Get step-by-step instructions for assembly and soldering
- Summarize and document pickup configurations


The logic and user interface are implemented in Python. The AI assistant leverages a language model (LLM) to provide context-aware guidance, explanations, and suggestions throughout the pickup design process. This makes the tool suitable for both beginners and experienced guitar enthusiasts.

## How AI is Used and Configured

The application uses a language model (LLM) to:
- Interpret user input and provide step-by-step guidance
- Explain technical concepts related to guitar pickups and wiring
- Suggest wiring modes, configurations, and troubleshooting tips
- Summarize and document the user's design choices

### AI Configuration

By default, the application is set up to use a local LLM backend (such as Ollama) for AI features. You can configure the AI backend and model using environment variables:

- `LLM_BACKEND`: Set to "ollama" to enable AI features (default)
- `OLLAMA_URL`: Ollama server URL (default: http://127.0.0.1:11434)
- `OLLAMA_MODEL`: Model to use (default: mistral)

Example (Windows command prompt):
```
set OLLAMA_MODEL=llama2
python start_web.py
```

## Project Structure

- `start_web.py`: Entry point to start the web application
- `app/`: Main application code
  - `main.py`: Main logic for running the app
  - `ai_assistant.py`: AI assistant logic
  - `logic.py`: Core logic for pickup configuration
  - `llm_client.py`: Handles communication with language models
  - `wiring.py`: Wiring logic and diagrams
  - `humbucker.py`: Humbucker pickup data structures
  - `steps/`: Step-by-step modules for each part of the process
	 - `step_measurements.py`, `step_pole_assignment.py`, etc.
  - `requirements.txt`: Python dependencies

## How to Use

1. **Install dependencies**
	- Run `pip install -r app/requirements.txt`
2. **Start the application**
	- Run `python start_web.py`
3. **Follow the instructions**
	- The assistant will guide you through the process of designing and configuring a humbucker pickup.

## Features
- Interactive, step-by-step guidance
- AI-powered suggestions and explanations
- Customizable pickup parameters
- Wiring and switch configuration help
- Assembly and soldering instructions

## Requirements
- Python 3.8 or newer
- Internet connection (for AI features)

## License
This project is for educational purposes as part of the course "Utilizing Generative AI" (Finnish: "Generatiivisen tekoälyn hyödyntäminen").
