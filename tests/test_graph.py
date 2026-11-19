"""오프라인 시험: 허브 API를 부르지 않고 저장된 자료(data/graph/*.sqlite)로 jeju-agent 기대값을 재현한다.
실행: python -m pytest -q tests
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["LLM_MODE"] = "off"
os.environ["GRAPH_OFFLINE"] = "1"

from graph import engine as en
from graph import pipeline as pp


# 모델(qwen3:4b)이 지시문대로 낼 해석 결과를 고정값으로 둔다(시험은 계산·검증만 확인)
SLOTS = {
    "cafe": {"places": ["애월읍", "한림읍"], "concepts": ["점포수", "방문인구"], "filters": {"업종": "카페"}, "period": None,
             "analysis": "ratio", "ratio": {"numerator": "점포수", "denominator": "방문인구", "scale": 10000}, "unsupported": ""},
    "cvs": {"places": ["한림읍"], "concepts": ["점포수"], "filters": {"업종": "편의점"}, "period": None,
            "analysis": "count", "ratio": None, "unsupported": ""},
    "visit": {"places": ["노형동", "연동"], "concepts": ["방문인구"], "filters": {}, "period": ("2026-08-01", "2026-08-31"),
              "analysis": "compare", "ratio": None, "unsupported": ""},
}


def _row(res, word):
    return next(r for r in res.rows if word in r["지표"])


def test_cafe_density_matches_jeju_agent():
    res = pp.run("애월에 카페가 너무 많을까요?", SLOTS["cafe"])
    m = next(m for m in res.metrics if m.kind == "ratio" and "카페" in m.name and "방문" in m.name)
    assert round(m.values["애월읍"], 2) == 8.32
    assert round(m.values["한림읍"], 2) == 11.41
    cnt = next(m for m in res.metrics if m.name == "카페 점포 수")
    assert cnt.values["애월읍"] == 228 and cnt.values["한림읍"] == 152
    assert 793 in res.used and 583 in res.used


def test_count_convenience_store():
    res = pp.run("한림읍 편의점은 몇 개야?", SLOTS["cvs"])
    assert _row(res, "편의점 점포 수")["대상 값"] == 59


def test_visit_index_compare():
    res = pp.run("2026년 8월 노형동과 연동의 방문객 비교해줘", SLOTS["visit"])
    m = next(m for m in res.metrics if "방문" in m.name and m.kind == "daily_mean")
    assert round(m.values["노형동"], 2) == 230606.48
    assert round(m.values["연동"], 2) == 246548.48


def test_index_unit_never_summed():
    m, _, _ = en.choose_measure("방문인구", {}, "읍면동")
    assert m.unit == "지표" and m.op == "daily_mean"
    m.op = "sum"
    assert en.validate(m, ("2026-08-01", "2026-08-31"))


def test_card_store_count_not_used_as_regional_denominator():
    m, _, rej = en.choose_measure("점포수", {}, "읍면동")
    assert m.dataset != 746


def test_guard_removes_ungrounded_values(monkeypatch):
    """모델이 질문에 없는 값을 내면 코드가 지운다('바꿀까'의 '바', 지어낸 날짜, 질문에 없는 지명)."""
    os.environ["LLM_MODE"] = "on"
    from agent import llm
    from graph import interpret as it
    S = it._schema()
    fake = {"places": ["이도2동", "한림"], "concepts": ["충전기수"], "filters": [{"concept": "업종", "value": "바"}],
            "period": {"start": "2025-01-01", "end": "2025-01-31"}, "analysis": "lookup", "ratio": None, "unsupported": ""}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (S.model_validate(fake), {}))
    s, rec = it.interpret("이도2동에 전기차 충전소 충분해? 차를 전기차로 바꿀까 고민 중이야")
    os.environ["LLM_MODE"] = "off"
    assert s["places"] == ["이도2동"] and s["filters"] == {} and s["period"] is None and s["concepts"] == ["충전기수"]


def test_no_code_interpretation_when_model_off():
    from graph import interpret as it
    s, rec = it.interpret("애월에 카페 많아?")
    assert not s["concepts"] and rec["ask"]
