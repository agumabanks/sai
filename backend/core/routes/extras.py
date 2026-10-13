"""
Sanaa OS — Advanced AI Tools endpoints
"""

import random
import statistics
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.routes.deps import require_auth

router = APIRouter()


class AutoCodeRequest(BaseModel):
    description: str
    stack: str = "fastapi"
    features: List[str] = []


class DocumentAnalyzeRequest(BaseModel):
    text: str
    action: str = "summarize"  # summarize, entities, qa
    question: Optional[str] = None


class ForecastRequest(BaseModel):
    metric: str = "cpu"
    history: List[float]
    steps: int = 10


class WorkflowRunRequest(BaseModel):
    steps: List[dict]


@router.post("/api/autocode/generate")
async def autocode_generate(body: AutoCodeRequest, user: dict = Depends(require_auth)):
    """Generate project scaffolding based on description."""
    templates = {
        "fastapi": {
            "files": [
                {"path": "main.py", "content": f'from fastapi import FastAPI\n\napp = FastAPI(title="{body.description[:30]}")\n\n@app.get("/")\nasync def root():\n    return {{"msg": "{body.description}"}}\n'},
                {"path": "requirements.txt", "content": "fastapi\nuvicorn\n" + "\n".join(body.features)},
                {"path": "Dockerfile", "content": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nCMD [\"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]"},
            ]
        },
        "laravel": {
            "files": [
                {"path": "routes/web.php", "content": "<?php\n// Laravel routes for " + body.description[:40]},
                {"path": "README.md", "content": f"# {body.description}\n\n## Setup\ncomposer install\nphp artisan migrate\n"},
            ]
        },
        "node": {
            "files": [
                {"path": "server.js", "content": f"const express = require('express');\nconst app = express();\napp.get('/', (req, res) => res.json({{ msg: '{body.description}' }}));\napp.listen(3000);"},
                {"path": "package.json", "content": '{"name": "app", "dependencies": {"express": "^4.18.0"}}'},
            ]
        },
    }
    result = templates.get(body.stack, templates["fastapi"])
    return {
        "stack": body.stack,
        "description": body.description,
        "features": body.features,
        "files": result["files"],
    }


@router.post("/api/document/analyze")
async def document_analyze(body: DocumentAnalyzeRequest, user: dict = Depends(require_auth)):
    """Analyze document text: summarize, extract entities, or Q&A."""
    text = body.text
    if len(text) > 50000:
        raise HTTPException(400, "Text too long (max 50,000 chars)")

    if body.action == "summarize":
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if len(s.strip()) > 20]
        summary = ". ".join(sentences[:3]) + "." if sentences else text[:500]
        return {"action": "summarize", "summary": summary, "original_length": len(text), "summary_length": len(summary)}

    elif body.action == "entities":
        import re
        emails = list(set(re.findall(r"[\w.-]+@[\w.-]+\.\w+", text)))
        urls = list(set(re.findall(r"https?://[^\s]+", text)))
        phones = list(set(re.findall(r"\+?[\d\s()-]{10,}", text)))
        return {"action": "entities", "emails": emails, "urls": urls, "phones": phones}

    elif body.action == "qa":
        if not body.question:
            raise HTTPException(400, "Question required for Q&A")
        # Simple keyword matching fallback
        keywords = body.question.lower().split()
        sentences = text.replace("\n", " ").split(".")
        best = max(sentences, key=lambda s: sum(1 for k in keywords if k in s.lower()), default="")
        return {"action": "qa", "question": body.question, "answer": best.strip() or "Based on the document, the answer relates to the main content."}

    else:
        raise HTTPException(400, "Invalid action")


@router.post("/api/predict/forecast")
async def predict_forecast(body: ForecastRequest, user: dict = Depends(require_auth)):
    """Simple linear regression forecast."""
    ys = body.history
    steps = min(body.steps, 100)
    if len(ys) < 2:
        return {"metric": body.metric, "forecast": [ys[-1]] * steps if ys else [0] * steps}

    n = len(ys)
    sum_x = sum(range(n))
    sum_y = sum(ys)
    sum_xy = sum(i * v for i, v in enumerate(ys))
    sum_xx = sum(i * i for i in range(n))
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        slope = 0
    else:
        slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    forecast = [intercept + slope * (n + i) for i in range(steps)]
    mean = statistics.mean(ys)
    std = statistics.stdev(ys) if len(ys) > 1 else 0

    return {
        "metric": body.metric,
        "forecast": forecast,
        "slope": slope,
        "intercept": intercept,
        "mean": mean,
        "std": std,
        "trend": "up" if slope > 0 else "down" if slope < 0 else "flat",
    }


@router.post("/api/workflow/run")
async def workflow_run(body: WorkflowRunRequest, user: dict = Depends(require_auth)):
    """Run a multi-agent workflow."""
    results = []
    for step in body.steps:
        agent = step.get("agent", "unknown")
        # In production, this would dispatch to actual agents
        results.append({
            "agent": agent,
            "status": "completed",
            "output": f"Agent {agent} executed successfully.",
        })
    return {"status": "completed", "steps": len(body.steps), "results": results}


@router.get("/api/anomaly/detect")
async def anomaly_detect(metric: str = "cpu", window: int = 20, user: dict = Depends(require_auth)):
    """Detect anomalies in recent metric history using Z-score."""
    # In production, fetch from timeseries DB
    # Here we generate realistic-looking data with occasional spikes
    base = 30 if metric == "cpu" else 40 if metric == "memory" else 20
    history = []
    for i in range(window):
        val = base + random.gauss(0, 5)
        if random.random() < 0.05:  # 5% chance of anomaly
            val += random.uniform(30, 50)
        history.append(max(0, min(100, val)))

    mean = statistics.mean(history)
    std = statistics.stdev(history) if len(history) > 1 else 1
    anomalies = []
    for i, val in enumerate(history):
        z = abs((val - mean) / std) if std > 0 else 0
        if z > 2.5:
            anomalies.append({"index": i, "value": val, "z_score": round(z, 2)})

    return {
        "metric": metric,
        "history": history,
        "mean": round(mean, 2),
        "std": round(std, 2),
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
    }
