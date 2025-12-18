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
        self.ollama_url = ollama_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
        # Default model name; user can override with env var OLLAMA_MODEL
        self.model = model or os.environ.get("OLLAMA_MODEL", "mistral")

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

    def embeddings(self, texts, timeout: int = 10):
        """Compute embeddings for a list of texts using the Ollama-like endpoint.

        Returns a dict: {'ok': bool, 'embeddings': list or None, 'error': str}
        """
        if self.backend != "ollama":
            return {'ok': False, 'embeddings': None, 'error': 'LLM backend not configured for Ollama'}

        # Try common embeddings endpoint shapes
        endpoints = [
            '/v1/embeddings',
            '/api/embeddings',
        ]
        headers = {'Content-Type': 'application/json'}
        payload = {'model': self.model, 'input': texts}

        for ep in endpoints:
            try:
                url = f"{self.ollama_url}{ep}"
                r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            except Exception as e:
                last_err = str(e)
                continue
            try:
                r.raise_for_status()
            except Exception:
                last_err = f'Status {r.status_code}: {r.text[:200]}'
                continue

            try:
                j = r.json()
                # Try OpenAI-like response shape
                if isinstance(j, dict) and 'data' in j:
                    embs = [d.get('embedding') for d in j.get('data')]
                    return {'ok': True, 'embeddings': embs, 'error': ''}
                # Try direct list
                if isinstance(j, list):
                    return {'ok': True, 'embeddings': j, 'error': ''}
                # Fallback: maybe key 'embeddings'
                if isinstance(j, dict) and 'embeddings' in j:
                    return {'ok': True, 'embeddings': j.get('embeddings'), 'error': ''}
                return {'ok': False, 'embeddings': None, 'error': 'Unknown embeddings response: ' + str(j)[:200]}
            except Exception as e:
                last_err = str(e)
                continue

        return {'ok': False, 'embeddings': None, 'error': last_err}


# Small FAQ + wrapper that first checks a local knowledge base, then falls back
# to an LLM backend (SimpleLLM) if requested/available.
_FAQ = [
    (['solder', 'soldering', 'iron', 'tips'],
     "Soldering tips: use a 25–40W iron with a clean, tinned tip. Use rosin-core flux for electronics. "
     "Heat the joint (pad + wire) and feed solder to the joint, not the iron. Tin stranded wires first, keep joints brief, "
     "and work in a ventilated area. Safety: wear eye protection and avoid breathing flux fumes."),

    (['hum', 'hum cancelling', 'humming', 'cancel'],
     "Hum-cancelling pickups require reverse magnetic polarity and reverse electrical wiring (RWRP) for one coil relative to the other. "
     "In practice, a humbucker has two coils wound oppositely and mounted with opposite magnetic polarity so noise cancels. To check: "
     "measure phase with a meter or listen—if you short the two coils and the hum reduces, polarity is correct."),

    (['ground', 'bare', 'shield', 'grounding'],
     "Grounding guidance: tie the bare drain wire to the pot casing (common ground point) and the bridge ground. Keep ground connections short and solid. "
     "Avoid daisy-chaining long ground wires; star the ground when possible for the cleanest result."),

    (['series', 'series link', 'series connection', 'series join'],
     "Series wiring: to connect coils in series (typical humbucker), solder the end of coil A to the start of coil B (the two middle wires). Insulate that join if it's not the output. The remaining free ends are HOT and GROUND."),

    (['flux', 'tinning'],
     "Flux and tinning: Use rosin-core or separate rosin flux for electronics. Tinning the iron and wires before soldering improves heat transfer and makes clean joints easier.")
]


def _local_faq_answer(question: str) -> str:
    if not question:
        return ''
    q = question.lower()
    # Simple keyword matching: return the first FAQ that matches any keyword
    for keys, answer in _FAQ:
        for k in keys:
            if k in q:
                return answer
    return ''


def answer(question: str, prefer_llm: bool = False, max_tokens: int = 400) -> str:
    """Return a short answer for common wiring/soldering questions.

    Behavior:
    - Check a small local FAQ first and return that if matched.
    - If no FAQ match and `prefer_llm` is True and Ollama backend is configured, call the LLM.
    - Otherwise return a helpful fallback note.
    """
    q = (question or '').strip()
    if not q:
        return ''

    # Local FAQ match
    faq = _local_faq_answer(q)
    if faq:
        return faq

    # If user requested LLM and backend is available, call it
    try:
        llm = SimpleLLM()
        if prefer_llm and llm.backend == 'ollama':
            prompt = f"Answer briefly and practically: {q}\nInclude safety notes where relevant."
            resp = llm.generate(prompt, max_tokens=max_tokens)
            return resp or "(LLM returned empty response)"
    except Exception:
        # Fall through to fallback
        pass

    return "I don't have a canned answer for that exact question. Try rephrasing or enable LLM backend by setting `LLM_BACKEND=ollama`."
