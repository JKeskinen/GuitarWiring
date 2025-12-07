#!/usr/bin/env python
"""
Start the local AI server and Streamlit web server for the GuitarWiring application.
"""

import subprocess
import sys
import os
import time
import threading

def start_ollama():
    """Start the Ollama local AI server in its own PowerShell window."""
    try:
        print("Starting Ollama local AI server in a new window...")
        # Use 'start' command to open a new PowerShell window
        os.system('start powershell -NoExit -Command "ollama serve"')
        print("Ollama server window opened. It will run on http://127.0.0.1:11434")
        time.sleep(5)  # Give Ollama time to start
    except Exception as e:
        print(f"Warning: Could not start Ollama: {e}")

def start_streamlit():
    """Start the Streamlit web server."""
    try:
        print("Starting Streamlit app...")
        # Use the virtual environment's Python
        venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "python.exe")
        if os.path.exists(venv_python):
            python_cmd = venv_python
        else:
            python_cmd = sys.executable
        
        subprocess.run(
            [python_cmd, "-m", "streamlit", "run", "app/main.py"],
            check=False
        )
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except Exception as e:
        print(f"Error starting Streamlit: {e}")
        sys.exit(1)

def main():
    # Change to the app directory
    app_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(app_dir)
    
    # Start Ollama in a background thread
    ollama_thread = threading.Thread(target=start_ollama, daemon=True)
    ollama_thread.start()
    
    # Start Streamlit in the main thread
    start_streamlit()

if __name__ == "__main__":
    main()
