"""종합 답변: 사용자 질문과 코드가 계산한 결과(사실 목록)를 로컬 LLM이 읽고, 질문에 대한 '결론 + 근거'를 쓴다.
  answer: 질문에 바로 답하는 한 문장(예: "경쟁이 심한 편은 아닙니다.")
  reason: 그 근거 한 문장(계산 결과의 숫자·기준 시점을 그대로)

- LLM에는 계산된 사실만 준다. LLM은 계산하지 않고, 사실에 있는 숫자만 옮겨 쓴다.
- 숫자 검사: 답변 속 숫자가 사실 목록·질문에 모두 있어야 통과. 하나라도 없으면 버리고 코드 문장(쉬운 말 요약)을 보여 준다.
- 추천·결정 문장('차려도 됩니다' 등)이 있으면 버린다.
"""
from __future__ import annotations

import re
import time
from functools import lru_cache
from pathlib import Path

from graph import pipeline as pp

ROOT = Path(__file__).resolve().parents[1]
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
KIND_KO = {"count": "개수", "sum": "합계", "mean": "평균", "daily_mean": "일평균", "ratio": "비율"}


def _schema():
    from pydantic import BaseModel, Field

    class GAnswer(BaseModel):
        answer: str = Field(min_length=4, max_length=200)
        reason: str = Field(min_length=10, max_length=500)

    return GAnswer


def register_schema():
    from agent.schemas import SCHEMAS
    SCHEMAS.setdefault("graph_answer", _schema())


@lru_cache(maxsize=1)
def _prompt_text() -> tuple[str, str]:
    text = (ROOT / "agent" / "prompts" / "graph_answer.md").read_text(encoding="utf-8")
    system, user = text.split("### user", 1)
    return system.replace("### system", "").strip(), user.strip()


def facts(res: pp.Result) -> list[str]:
    """계산 결과를 한 줄씩 사실로(숫자는 화면과 같은 형식으로)."""
    out = []
    if res.slots.get("unsupported"):
        out.append(f"데이터로 답할 수 없는 요구: {res.slots['unsupported']} (관측 자료로 예측하거나 없는 값을 만들지 않음)")
    if res.lead:
        out.append(f"결론(코드 계산): {res.lead}")
    byid = {m.id: m for m in res.metrics}
    for r in res.rows:
        m = byid[r["id"]]
        kind = "질문한 지표" if getattr(m, "asked", False) else "함께 본 지표"
        if m.reason:
            out.append(f"[{kind}] {m.name}: 계산하지 못함 — {m.reason}")
            continue
        per = m.period if "기준" in (m.period or "") else f"{m.period} 기준"
        s = f"[{kind}] {m.name} ({per})"
        if r.get("대상") and r.get("대상 값") is not None:
            s += f": {r['대상']} {pp.fmt(r['대상 값'], m.unit, m.digits)}"
            if r.get("순위"):
                s += f", 제주 읍면동 {r['비교 수']}곳 중 {r['순위']}위({pp.VERDICT.get(r['판정'], r['판정'])})"
            if r.get("제주 중앙값") is not None:
                s += f", 제주 중앙값 {pp.fmt(r['제주 중앙값'], m.unit, m.digits)}"
        elif r.get("사유"):
            s += f": {r['사유']}"
        out.append(s)
        if len(res.places) > 1:
            v = m.values.reindex(res.places).dropna()
            if len(v) >= 2:
                out.append(f"  지역 비교 {m.name}: " + ", ".join(f"{a} {pp.fmt(float(x), m.unit, m.digits)}" for a, x in v.items()))
        if not res.places and getattr(m, "asked", False):
            v = m.values.dropna().sort_values(ascending=False)
            if len(v) >= 3:
                out.append(f"  {m.name} 상위 3곳: " + ", ".join(f"{a} {pp.fmt(float(x), m.unit, m.digits)}" for a, x in v.iloc[0:3].items()))
        if m.trend is not None and len(m.trend) >= 2:
            a, b = float(m.trend.iloc[0]), float(m.trend.iloc[-1])
            ch = f" ({(b / a - 1) * 100:+.1f}%)" if a else ""
            out.append(f"  {m.name} 월별 변화: {m.trend.index[0]} {pp.fmt(a, m.unit, m.digits)} → {m.trend.index[-1]} {pp.fmt(b, m.unit, m.digits)}{ch}"
                       + (f", 자료 없는 달 {', '.join(getattr(m, 'missing', []))}" if getattr(m, "missing", None) else ""))
    if res.cross:
        c = res.cross
        out.append(f"조건 교차: {c['desc']}: {', '.join(c['hits']) or '없음'} ({len(c['hits'])}곳)")
    out += [f"자료 설명: {n}" for n in res.notes_top]
    out += [f"주의: {w.lstrip('⚠ ')}" for w in res.warnings]
    return out


def _nums(text: str) -> set[str]:
    out = set()
    for t in NUM.findall(text):
        t = t.replace(",", "")
        if "." in t:
            t = t.rstrip("0").rstrip(".")
        out.add(t.lstrip("0") or "0")
    return out


HANGUL = re.compile(r"[가-힣]")


def check(answer: str, allowed_text: str, reason: str | None = None) -> list[str]:
    """답변 속 숫자 중 사실·질문에 없는 것, 추천·결정 문장, 내용 없는 답('...?' 등)."""
    bad = sorted(_nums(answer) - _nums(allowed_text))
    errs = [f"사실에 없는 숫자 {', '.join(bad)}"] if bad else []
    errs += [f"추천·결정 표현 '{b}'" for b in pp.BANNED if b in answer]
    if reason is not None:
        head = answer[: max(0, len(answer) - len(reason))]
        if len(HANGUL.findall(head)) < 4:
            errs.append("결론 문장에 내용이 없음")
        if len(HANGUL.findall(reason)) < 10 or not (_nums(reason) & _nums(allowed_text)):
            errs.append("근거 문장에 계산 결과(숫자)가 없음")
    return errs


def answer(res: pp.Result) -> dict:
    """{'text', 'ok', 'errors', 'sec', 'facts'}. 실패하면 ok=False(화면은 코드 문장을 보여 준다)."""
    from agent import llm
    t0 = time.time()
    fs = facts(res)
    rec = {"text": "", "ok": False, "errors": [], "sec": 0.0, "facts": fs}
    if llm.llm_mode() == "off" or not [m for m in res.metrics if not m.reason] and not res.slots.get("unsupported"):
        rec["errors"].append("모델이 꺼져 있거나 계산된 결과가 없음")
        return rec
    register_schema()
    sys_p, user_t = _prompt_text()
    user_p = user_t.replace("{question}", res.question).replace("{facts}", "\n".join(f"- {f}" for f in fs))
    allowed = "\n".join(fs) + "\n" + res.question
    tries = []
    for attempt in range(2):  # 숫자 검사에 걸리면 무엇이 틀렸는지 알려 주고 한 번 더 쓰게 한다
        out, st = llm.chat("graph_answer", sys_p, user_p, options={"num_ctx": 6144, "num_predict": 700})
        rec["stats"] = st
        if out is None:
            rec["errors"] = [st.get("error") or st.get("validation_error") or "응답 없음"]
            break
        ans, why = out.answer.strip(), out.reason.strip()
        text = f"{ans} {why}"
        errs = check(text, allowed, reason=why)
        tries.append({"text": text, "errors": errs})
        rec.update(text=text, answer=ans, reason=why, errors=errs, ok=not errs)
        if not errs:
            break
        user_p = (user_t.replace("{question}", res.question).replace("{facts}", "\n".join(f"- {f}" for f in fs))
                  + f"\n\n앞의 답변은 고쳐야 합니다: {'; '.join(errs)}. 계산 결과에 적힌 숫자만 그대로 옮겨 쓰고, "
                    "계산 결과에 없는 숫자(새로 계산하거나 반올림한 값, '배', 날짜 바꿔 쓰기)는 빼고 다시 쓰세요.")
    rec["tries"] = tries
    rec["sec"] = round(time.time() - t0, 2)
    return rec
