"""로컬 언어모델 호출 (지시서 §7). Ollama만 쓴다 — 외부 AI API는 호출하지 않는다.

- temperature 0, num_ctx 4096, num_predict 300, 출력은 JSON 스키마로 강제(format)
- pydantic 검증 실패 시 1회 재시도, 그래도 실패하면 None(화면이 선택지를 띄움)
- 호출마다 prompt_eval_count·eval_count·eval_duration·total_duration을 metrics/llm_calls.jsonl에 남긴다
- 모델 이름은 .env의 OLLAMA_MODEL, LLM_MODE=off면 호출하지 않는다
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.request
from pathlib import Path

from pydantic import BaseModel, ValidationError

from agent.schemas import SCHEMAS

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "agent" / "prompts"
METRICS = ROOT / "metrics" / "llm_calls.jsonl"
# localhost 이름 풀이가 Windows에서 약 2초 늦어(2단계 측정) 주소를 직접 쓴다
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


def _env(name: str, default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default


def model_name() -> str:
    return _env("OLLAMA_MODEL", "qwen3:4b")


def llm_mode() -> str:
    return _env("LLM_MODE", "on").lower()


def prompt(name: str, **values) -> tuple[str, str]:
    """prompts/{name}.md 를 '### system' / '### user' 두 부분으로 읽고 {자리}를 채운다."""
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    system, user = text.split("### user", 1)
    system = system.replace("### system", "").strip()
    user = user.strip()
    for k, v in values.items():
        user = user.replace("{" + k + "}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return system, user


def _log(rec: dict) -> None:
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    with METRICS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def chat(call: str, system: str, user: str, *, options: dict | None = None) -> tuple[BaseModel | None, dict]:
    """(검증된 출력 또는 None, 측정값). LLM_MODE=off면 (None, {"mode": "off"})."""
    if llm_mode() == "off":
        return None, {"call": call, "mode": "off"}
    schema = SCHEMAS[call]
    body = {"model": model_name(), "stream": False, "format": schema.model_json_schema(),
            # seed 고정: temperature 0에서도 실행마다 선택이 달라지는 경우가 있어(7단계 시험) 재현성을 위해 고정
            "options": {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 400, **(options or {})},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    num_gpu = _env("OLLAMA_NUM_GPU", "")
    if num_gpu != "":  # 성능 측정용: 0이면 CPU 전용(지시서 §10-9)
        body["options"]["num_gpu"] = int(num_gpu)
    num_thread = _env("OLLAMA_NUM_THREAD", "")
    if num_thread != "":  # 성능 측정용: 센터 PC(i7-8700, 6코어)를 흉내 내려고 CPU 스레드 수를 제한
        body["options"]["num_thread"] = int(num_thread)
    if model_name().startswith("qwen3"):
        body["think"] = False
    stats = {"call": call, "model": model_name(), "attempts": 0, "ok": False}
    for attempt in range(2):  # 검증 실패 시 1회 재시도
        stats["attempts"] = attempt + 1
        t = time.time()
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                resp = json.load(r)
        except Exception as e:
            stats["error"] = f"{type(e).__name__}: {e}"
            break
        rec = {k: resp.get(k) for k in ("prompt_eval_count", "eval_count", "eval_duration", "total_duration",
                                        "load_duration", "prompt_eval_duration")}
        rec.update({"wall_s": round(time.time() - t, 3), "at": dt.datetime.now().isoformat(timespec="seconds")})
        stats.setdefault("calls", []).append(rec)
        try:
            out = schema.model_validate_json(resp["message"]["content"])
            stats["ok"] = True
            _log({**stats, **rec})
            return out, stats
        except ValidationError as e:
            stats["validation_error"] = str(e)[:300]
    _log(stats)
    return None, stats
