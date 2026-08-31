from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.schema import AssessmentReport

def _ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


class LlmError(Exception):
    def __init__(self, message: str, *, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise LlmError("The model did not return JSON. Try a larger local model or retry.")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise LlmError("The model returned JSON that was not an object.")
    return data


def complete_json(system: str, user: str, *, timeout: float = 180.0) -> dict[str, Any]:
    url = f"{_ollama_host()}/api/chat"
    payload = {
        "model": _ollama_model(),
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0.2},
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
    except httpx.ConnectError as exc:
        raise LlmError(
            "Cannot reach Ollama at "
            f"{_ollama_host()}. Install Ollama, start it, and pull a model "
            f"(default: {_ollama_model()})."
        ) from exc
    except httpx.TimeoutException as exc:
        raise LlmError(
            "Ollama timed out. CPU inference can be slow; wait and retry, "
            "or use a smaller model via OLLAMA_MODEL (e.g. llama3.2:3b)."
        ) from exc

    if response.status_code >= 400:
        detail = response.text[:400]
        raise LlmError(
            f"Ollama returned HTTP {response.status_code}: {detail}",
            status_code=502,
        )
    body = response.json()
    content = (body.get("message") or {}).get("content") or ""
    if not content:
        raise LlmError("Ollama returned an empty response.")
    return _extract_json(content)


def parse_report(data: dict[str, Any]) -> AssessmentReport:
    risks = data.get("key_risks") or []
    steps = data.get("next_implementation_steps") or []
    if isinstance(risks, str):
        risks = [r.strip() for r in risks.split("\n") if r.strip()]
    if isinstance(steps, str):
        steps = [s.strip() for s in steps.split("\n") if s.strip()]
    data = {**data, "key_risks": risks, "next_implementation_steps": steps}
    if "implementation_complexity_band" not in data:
        data["implementation_complexity_band"] = "Medium"
    return AssessmentReport.model_validate(data)


def generate_report(system: str, user: str) -> AssessmentReport:
    data = complete_json(system, user)
    try:
        return parse_report(data)
    except Exception:
        retry_user = (
            user
            + "\n\nPREVIOUS OUTPUT WAS INVALID. Return only a JSON object matching the schema."
        )
        data = complete_json(system, retry_user)
        return parse_report(data)


def ollama_reachable() -> dict[str, Any]:
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{_ollama_host()}/api/tags")
        names = []
        if r.status_code == 200:
            names = [m.get("name") for m in r.json().get("models") or [] if m.get("name")]
        model = _ollama_model()
        return {
            "ok": r.status_code == 200,
            "host": _ollama_host(),
            "model": model,
            "models": names,
            "model_present": any(
                model == n or n.startswith(model.split(":")[0]) for n in names
            ),
        }
    except httpx.HTTPError:
        return {
            "ok": False,
            "host": _ollama_host(),
            "model": _ollama_model(),
            "models": [],
            "model_present": False,
        }
