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
            "period": {"start": "2025-01-01", "end": "2025-01-31"}, "analysis": "lookup", "ratio": None, "goal": [], "unsupported": ""}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (S.model_validate(fake), {}))
    s, rec = it.interpret("이도2동에 전기차 충전소 충분해? 차를 전기차로 바꿀까 고민 중이야")
    os.environ["LLM_MODE"] = "off"
    assert s["places"] == ["이도2동"] and s["filters"] == {} and s["period"] is None and s["concepts"] == ["충전기수"]


def test_no_code_interpretation_when_model_off():
    from graph import interpret as it
    s, rec = it.interpret("애월에 카페 많아?")
    assert not s["concepts"] and rec["ask"]


# ---------------- v2 ----------------

def _slots(**k):
    base = {"places": [], "concepts": [], "filters": {}, "period": None, "analysis": "lookup", "ratio": None,
            "goal": [], "unsupported": ""}
    base.update(k)
    return base


def test_anchor_out_of_range():
    """상권 렌즈(상가 2025-09 스냅샷)와 함께여도 카드 자료(746, ~2021-05)는 자기 최신 달로 계산한다."""
    res = pp.run("삼도동 카페들 매출은 어느 정도야?",
                 _slots(places=["삼도1동"], concepts=["카드이용금액"], filters={"업종": "카페"}))
    m = next(m for m in res.metrics if "카드이용금액" in m.name)
    assert not m.reason and m.period.startswith("2021-05")
    assert any("같은 시점으로 맞추지 못하고" in l for l in res.limits)


def test_lead_compare():
    res = pp.run("애월이랑 한림 중에 관광객이 더 많이 오는 곳은 어디야?",
                 _slots(places=["애월읍", "한림읍"], concepts=["방문인구"], analysis="compare"))
    assert res.lead.startswith("애월읍이 더 높습니다")


def test_lead_trend():
    res = pp.run("요즘 노형동 사람 많이 줄었어?", _slots(places=["노형동"], concepts=["방문인구"], analysis="trend"))
    assert res.lead.split(" — ")[0] in ("늘었습니다", "줄었습니다", "큰 변화가 없습니다")
    assert "%" in res.lead
    m = next(m for m in res.metrics if m.trend is not None)
    if m.missing:
        assert "자료가 없어 빠졌습니다" in res.lead


def test_concept_note():
    res = pp.run("애월이랑 한림 중에 관광객이 더 많이 오는 곳은 어디야?",
                 _slots(places=["애월읍", "한림읍"], concepts=["방문인구"], analysis="compare"))
    assert any("'관광객'" in n and "방문지표" in n for n in res.notes_top)


def test_no_dev_notes():
    res = pp.run("구좌읍에 편의점 하나 내볼까 하는데 경쟁 어때?",
                 _slots(places=["구좌읍"], concepts=["점포수"], filters={"업종": "편의점"}, analysis="ratio",
                        ratio={"numerator": "점포수", "denominator": "방문인구", "scale": 10000}))
    import re
    assert not any(re.match(r"^[A-Za-z_]+:", l) for l in res.limits)


def test_chart_choice():
    from graph import charts
    r1 = pp.run("애월 한림 방문 비교", _slots(places=["애월읍", "한림읍"], concepts=["방문인구"], analysis="compare"))
    assert charts.choose_charts(r1, r1.slots)[0][0] == "지역 비교"
    r2 = pp.run("노형동 추이", _slots(places=["노형동"], concepts=["방문인구"], analysis="trend"))
    assert charts.choose_charts(r2, r2.slots)[0][0] == "월별 추이"
    r3 = pp.run("한림읍 편의점", SLOTS["cvs"])
    assert charts.choose_charts(r3, r3.slots)[0][0] == "읍면동 순위"


def test_simple_count_lens_limit():
    res = pp.run("한림읍 편의점은 몇 개야?", SLOTS["cvs"])
    assert len([m for m in res.metrics if not getattr(m, "asked", False)]) <= pp.LENS_SIMPLE


def test_stale_warning():
    res = pp.run("삼도동 카페들 매출은 어느 정도야?",
                 _slots(places=["삼도1동"], concepts=["카드이용금액"], filters={"업종": "카페"}))
    assert any("2021-05" in w for w in res.warnings)


def test_ambiguous_place(monkeypatch):
    os.environ["LLM_MODE"] = "on"
    from agent import llm
    from graph import interpret as it
    S = it._schema()
    fake = {"places": ["삼도동"], "concepts": ["카드이용금액"], "filters": [{"concept": "업종", "value": "카페"}],
            "period": None, "analysis": "lookup", "ratio": None, "goal": [], "unsupported": ""}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (S.model_validate(fake), {}))
    s, rec = it.interpret("삼도동 카페들 매출은 어느 정도야?")
    os.environ["LLM_MODE"] = "off"
    assert rec["ask"] and [c["label"] for c in rec["choices"]][:2] == ["삼도1동", "삼도2동"]
    assert rec["choices"][-1]["places"] == ["삼도1동", "삼도2동"]


def test_cross_two_conditions():
    s = _slots(concepts=["외국인방문인구", "점포수"], filters={"업종": "한식"}, analysis="rank",
               ratio={"numerator": "점포수", "denominator": "방문인구", "scale": 10000},
               goal=[{"concept": "외국인방문인구", "want": "high"}, {"concept": "점포수", "want": "low"}])
    res = pp.run("외국인 손님 많은 동네에서 한식당 하고 싶은데 어디가 좋을까?", s)
    assert res.cross and res.cross["hits"] and "정해 드리지 않고" in res.lead
    assert int(res.cross["table"].values.sum()) >= pp.MIN_COMPARE


def test_guard_keeps_industry_with_shop_suffix():
    """'한식당'의 '한식'은 업종 낱말로 인정, '바꿀까'의 '바'는 아님."""
    from graph.interpret import _word_in
    assert _word_in("외국인 손님 많은 동네에서 한식당 하고 싶은데 어디가 좋을까?", "한식")
    assert _word_in("치킨집 몇 개야?", "치킨")
    assert not _word_in("차를 전기차로 바꿀까 고민 중이야", "바")


def test_review_fixes_missing_items(monkeypatch):
    """재점검(2차 모델 호출)이 고친 해석을 쓴다. 코드는 질문 낱말로 채우지 않는다."""
    os.environ["LLM_MODE"] = "on"
    os.environ["INTERPRET_REVIEW"] = "on"
    from agent import llm
    from graph import interpret as it
    S = it._schema()
    first = {"places": [], "concepts": ["점포수", "외국인방문인구"], "filters": [], "period": None, "analysis": "lookup",
             "ratio": None, "goal": [], "unsupported": ""}
    second = dict(first, filters=[{"concept": "업종", "value": "한식"}], analysis="rank",
                  ratio={"numerator": "점포수", "denominator": "방문인구", "scale": 10000},
                  goal=[{"concept": "외국인방문인구", "want": "high"}, {"concept": "점포수", "want": "low"}])
    monkeypatch.setattr(llm, "chat", lambda call, *a, **k: (S.model_validate(second if call == "graph_review" else first), {}))
    s, rec = it.interpret("외국인 손님 많은 동네에서 한식당 하고 싶은데 어디가 좋을까?")
    os.environ["LLM_MODE"] = "off"
    assert s["filters"] == {"업종": "한식"} and s["analysis"] == "rank" and len(s["goal"]) == 2
    assert set(rec["review"]["changed"]) >= {"filters", "goal", "analysis"}


def test_industry_value_must_exist_in_data():
    """업종 값은 업종 대응표·상가 자료의 업종 이름에 있어야 한다('외국인'·'버스'는 업종이 아님)."""
    from graph.interpret import industry_known
    assert industry_known("편의점") and industry_known("한식") and industry_known("빵")
    assert not industry_known("외국인") and not industry_known("버스")


def test_narrative_number_check(monkeypatch):
    """종합 답변(LLM): 계산 결과에 있는 숫자만 쓰면 통과, 없는 숫자를 쓰면 버리고 코드 문장을 쓴다."""
    os.environ["LLM_MODE"] = "on"
    from agent import llm
    from graph import narrate
    res = pp.run("애월이랑 한림 중에 관광객이 더 많이 오는 곳은 어디야?",
                 _slots(places=["애월읍", "한림읍"], concepts=["방문인구"], analysis="compare"))
    S = narrate._schema()
    good = {"answer": "애월읍에 더 많이 옵니다.",
            "reason": "2026-08 기준 일평균 방문지표가 애월읍 366,375, 한림읍 215,825로 애월읍이 더 높기 때문입니다."}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (S.model_validate(good), {}))
    rec = narrate.answer(res)
    assert rec["ok"], rec["errors"]
    assert rec["answer"].startswith("애월읍")
    bad = {"answer": "애월읍에 더 많이 옵니다.", "reason": "애월읍에는 하루 약 12만 명이 방문해 한림읍보다 15만 명 많기 때문입니다."}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (S.model_validate(bad), {}))
    rec = narrate.answer(res)
    os.environ["LLM_MODE"] = "off"
    assert not rec["ok"] and "사실에 없는 숫자" in rec["errors"][0]
