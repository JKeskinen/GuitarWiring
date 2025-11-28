"""
Ollama HTTP client for local Ollama server.

This `SimpleLLM` implementation sends generation requests to a local Ollama
server (default: http://localhost:11434). It expects an Ollama model to be
installed and available. If `LLM_BACKEND` env var is set to something else,
the class will fall back to a stub behaviour.

Reference: Ollama HTTP API (local) - POST /api/generate
"""
from typing import Optional
import os
import requests
import json


class SimpleLLM:
    def __init__(self, backend: Optional[str] = None, ollama_url: Optional[str] = None, model: Optional[str] = None):
        self.backend = backend or os.environ.get("LLM_BACKEND", "ollama")
        # Ollama server URL (default port 11434)
        self.ollama_url = ollama_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        # Default model name; user can override with env var OLLAMA_MODEL
        self.model = model or os.environ.get("OLLAMA_MODEL", "mistral:7b")

    def generate(self, prompt: str, max_tokens: int = 400) -> str:
        if self.backend != "ollama":
            # fallback stub
            return "LLM backend not configured for Ollama. Set LLM_BACKEND=ollama or update app/llm_client.py"
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}

        try:
            # Use streaming so we can handle chunked JSON objects (Ollama stream)
            resp = requests.post(url, data=json.dumps(payload), headers=headers, timeout=60, stream=True)
        except Exception as e:
            return f"Error connecting to Ollama server at {self.ollama_url}: {e}"

        try:
            resp.raise_for_status()
        except Exception:
            # If server returned non-2xx, give body for diagnostics
            return f"Ollama server returned {resp.status_code}: {resp.text}"

        parts = []

        # Iterate streamed lines and collect 'response' pieces or other common fields.
        try:
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                # Sometimes the stream sends multiple JSON objects per line or extra prefixes.
                # Try parse as JSON; if fails, append raw text fallback.
                try:
                    obj = json.loads(line)
                except Exception:
                    # If it's not JSON, append as-is (last resort)
                    parts.append(line)
                    continue

                # Common Ollama streaming chunk shape: {'model':..., 'response':'text chunk','done':false}
                if isinstance(obj, dict):
                    if "response" in obj:
                        parts.append(obj.get("response") or "")
                        # If done flag present and true, we could break, but continue to drain
                        continue

                    # Newer shape: choices/message/content or choices/text
                    choices = obj.get("choices")
                    if choices and isinstance(choices, list):
                        first = choices[0]
                        # message.content
                        msg = first.get("message")
                        if msg and isinstance(msg, dict) and "content" in msg:
                            parts.append(msg.get("content") or "")
                            continue
                        if "text" in first:
                            parts.append(first.get("text") or "")
                            continue

                    # Top-level text
                    if "text" in obj:
                        parts.append(obj.get("text") or "")
                        continue

                # Fallback: append stringified object
                parts.append(json.dumps(obj))

        except Exception:
            # If streaming iteration fails, fall back to try parse full body
            try:
                data = resp.json()
                # try previous non-stream parsing
                if isinstance(data, dict):
                    choices = data.get("choices")
                    if choices and isinstance(choices, list):
                        first = choices[0]
                        msg = first.get("message")
                        if msg and isinstance(msg, dict) and "content" in msg:
                            return msg["content"].strip()
                        if "text" in first:
                            return first["text"].strip()
                    if "text" in data:
                        return data["text"].strip()
                return resp.text
            except Exception:
                return f"Invalid JSON response from Ollama (stream failed): {resp.text}"

        # Join collected parts into one string and normalize whitespace
        result = "".join(parts).strip()
        return result if result else resp.text
