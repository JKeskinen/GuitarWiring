"""
Pieni FastAPI-serveri, joka palvelee static/index.html ja tarjoaa /analyze ja /generate -endpoints.
Aja: uvicorn server:app --reload
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import os

# Import your logic and LLM from app package
from app.logic import find_coil_pairs, detect_center_tap, make_connection_plan
from app.llm_client import SimpleLLM

app = FastAPI(title="Pickup Assistant API")

# Mount static directory (serve index.html from static/index.html)
if not os.path.isdir("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def read_index():
    path = "static/index.html"
    if not os.path.exists(path):
        return HTMLResponse("<h3>index.html not found in /static. Place static/index.html there.</h3>", status_code=404)
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

class AnalyzeRequest(BaseModel):
    wires: List[str]
    measurements: Dict[str, Optional[float]]

class GenerateRequest(BaseModel):
    meas: Dict[str, Optional[float]]
    analysis_text: str

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    # sanitize measurements: convert None to nan or skip
    meas = {}
    for k,v in req.measurements.items():
        try:
            meas[k] = float(v) if v is not None else float('nan')
        except:
            meas[k] = float('nan')
    pairs = find_coil_pairs(meas)
    center = detect_center_tap(meas, pairs)
    plan = make_connection_plan(pairs, center, req.wires or [])
    return JSONResponse({"pairs": pairs, "center": center, "plan": plan})

@app.post("/generate")
def generate(req: GenerateRequest):
    # Create a prompt that includes measurements and analysis_text
    prompt = (
        "You are a concise technical assistant. "
        "Given measurements and an analysis, produce a clear Finnish step-by-step guide "
        "for identifying pickup coils, testing polarity with a compass and checking/fixing phase. "
        f"Measurements: {req.meas}\n\nAnalysis summary:\n{req.analysis_text}\n\n"
        "Provide safety reminders and short juotosohjeet."
    )
    client = SimpleLLM()
    out = client.generate(prompt, max_tokens=400)
    return JSONResponse({"guide": out})

# If you want to run Python file directly:
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)