"""모델 해석 평가: eval/interpret_cases.jsonl의 질문마다 interpret()를 돌려 항목별 정답 여부를 잰다.

실행: python scripts/eval_interpret.py            (전체)
      python scripts/eval_interpret.py --kind 추이  (유형 하나)
결과: 화면 표 + eval/interpret_report.md

규칙: 프롬프트(agent/prompts/graph_interpret.md)를 바꿀 때마다 돌려 전체 정확도가 내려가지 않는지 본다.
틀린 유형은 프롬프트 예시를 더해 고친다(코드로 해석을 보정하지 않는다).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import llm  # noqa: E402
from graph.interpret import interpret  # noqa: E402

CASES = ROOT / "eval" / "interpret_cases.jsonl"
REPORT = ROOT / "eval" / "interpret_report.md"  # 재점검 끔이면 interpret_report_noreview.md


def _norm(v) -> str:
    return str(v).replace(" ", "")


def score(case: dict, s: dict, rec: dict) -> dict:
    # 지명: 되묻기를 기대하는 질문(오타·모호 지명)은 되묻기가 나오면 정답
    if case.get("ask"):
        place_ok = bool(rec.get("ask"))
    elif case.get("unsupported"):
        place_ok = True  # 답할 수 없는 요구는 unsupported로 막는 것이 핵심이라 지명은 채점하지 않는다
    else:
        place_ok = set(s.get("places") or []) == set(case["places"]) and not rec.get("ask")
    # 개념: 답할 수 없는 요구는 unsupported가 채워지면 정답, 잡담은 concepts가 비어야 정답
    got = set(s.get("concepts") or [])
    if case.get("unsupported"):
        concept_ok = bool(s.get("unsupported"))
    elif not case["concepts_any"]:
        concept_ok = not got
    else:
        concept_ok = all(any(c in got for c in grp) for grp in case["concepts_any"])
    # 구분값: 차원이 같고 값은 공백 무시 후 같거나 앞부분이 같으면 정답('치킨'·'치킨집')
    gf = s.get("filters") or {}

    def same(ef):
        return set(gf) == set(ef) and all(
            _norm(gf[k]) == _norm(ef[k]) or _norm(gf[k]).startswith(_norm(ef[k])) or _norm(ef[k]).startswith(_norm(gf[k]))
            for k in ef)
    # filters_ok: 둘 이상 정답이 있는 문항(예: '약국'은 구분값 없음 또는 의료기관종별=약국)
    filt_ok = any(same(ef) for ef in case.get("filters_ok") or [case["filters"]])
    # 잡담(잴 대상 없음)은 분석 유형을 채점하지 않는다
    ana_ok = True if (not case["concepts_any"] and not case.get("unsupported")) else s.get("analysis") in case["analysis"]
    period_ok = (list(s["period"]) if s.get("period") else None) == case.get("period")
    return {"지명": place_ok, "개념": concept_ok, "구분값": filt_ok, "분석": ana_ok, "기간": period_ok,
            "전체": place_ok and concept_ok and filt_ok and ana_ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default=None, help="유형 하나만(개수·밀도·비교·추이·순위·생활시설·불가·잡담·모호·오타)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cases", default=None, help="평가 세트 파일(기본 eval/interpret_cases.jsonl). 예: eval/interpret_holdout.jsonl")
    ap.add_argument("--no-review", action="store_true", help="모델 재점검(2차 호출) 없이 1차 해석만 평가")
    a = ap.parse_args()
    import os
    if a.no_review:
        os.environ["INTERPRET_REVIEW"] = "off"
    from graph.interpret import review_on
    if llm.llm_mode() == "off":
        print("LLM_MODE=off 입니다. .env에서 모델을 켜고 다시 실행하세요.")
        return
    src = Path(a.cases) if a.cases else CASES
    if not src.is_absolute():
        src = ROOT / src
    cases = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.kind:
        cases = [c for c in cases if c.get("kind") == a.kind]
    if a.limit:
        cases = cases[: a.limit]
    rows, secs = [], []
    for i, c in enumerate(cases, 1):
        t0 = time.time()
        s, rec = interpret(c["q"])
        sec = time.time() - t0
        secs.append(sec)
        sc = score(c, s, rec)
        rows.append({"case": c, "slots": s, "rec": rec, "score": sc, "sec": sec})
        mark = "O" if sc["전체"] else "X"
        wrong = ",".join(k for k, v in sc.items() if not v and k not in ("전체", "기간"))
        print(f"{i:>2}/{len(cases)} {mark} {sec:5.1f}s [{c.get('kind')}] {c['q'][:34]:<34} {('틀림: ' + wrong) if wrong else ''}")

    def acc(key, rs=rows):
        return sum(r["score"][key] for r in rs) / len(rs) if rs else 0

    keys = ["지명", "개념", "구분값", "분석", "전체"]
    fixed = sum(1 for r in rows if (r["rec"].get("review") or {}).get("changed"))
    lines = [f"# 모델 해석 평가 ({dt.datetime.now():%Y-%m-%d %H:%M}, {src.name}, 모델 {llm.model_name()}, {len(rows)}문항, "
             f"재점검 {'켬' if review_on() else '끔'})", "",
             "| 항목 | 정확도 | 목표 |", "|---|---|---|"]
    goal = {"지명": "90%", "개념": "90%", "전체": "85%"}
    for k in keys:
        lines.append(f"| {k} | {acc(k) * 100:.0f}% | {goal.get(k, '-')} |")
    if secs:
        lines.append(f"| 응답 시간 | 중앙값 {statistics.median(secs):.1f}초 · 최대 {max(secs):.1f}초 | - |")
    if review_on():
        lines.append(f"| 재점검이 고친 문항 | {fixed}개 | - |")
    lines += ["", "## 유형별", "", "| 유형 | 문항 | 전체 정확도 |", "|---|---|---|"]
    for kind in dict.fromkeys(r["case"].get("kind") for r in rows):
        rs = [r for r in rows if r["case"].get("kind") == kind]
        lines.append(f"| {kind} | {len(rs)} | {acc('전체', rs) * 100:.0f}% |")
    lines += ["", "## 틀린 문항", ""]
    for r in rows:
        if r["score"]["전체"]:
            continue
        c, s = r["case"], r["slots"]
        wrong = ", ".join(k for k, v in r["score"].items() if not v and k not in ("전체", "기간"))
        lines.append(f"- **{c['q']}** ({c.get('kind')}) — 틀림: {wrong}")
        lines.append(f"  - 기대: places={c['places']} concepts={c['concepts_any']} filters={c['filters']} "
                     f"analysis={c['analysis']}" + (" (되묻기)" if c.get("ask") else "") + (" (unsupported)" if c.get("unsupported") else ""))
        lines.append(f"  - 모델 1차: {json.dumps(r['rec'].get('raw'), ensure_ascii=False)}")
        if r["rec"].get("raw_review"):
            lines.append(f"  - 모델 재점검: {json.dumps(r['rec'].get('raw_review'), ensure_ascii=False)}")
        lines.append(f"  - 사용: places={s.get('places')} concepts={s.get('concepts')} filters={s.get('filters')} "
                     f"analysis={s.get('analysis')} unsupported='{s.get('unsupported')}' ask={r['rec'].get('ask')}")
    report = REPORT if review_on() else REPORT.with_name("interpret_report_noreview.md")
    if a.cases:
        report = report.with_name(report.stem + "_" + src.stem.replace("interpret_", "") + ".md")
    report.parent.mkdir(exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("\n".join(lines[:lines.index("## 틀린 문항")]))
    print(f"\n보고서: {report}")


if __name__ == "__main__":
    main()
