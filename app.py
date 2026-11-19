"""제주 데이터 상담 에이전트 — 화면 (B 화면 디자인 + A 지식 그래프 데이터 선별).

실행: streamlit run app.py
- 질문 → 로컬 LLM이 정해진 어휘로 해석 → 지식 그래프가 허브 1,259종 중 필요한 자료를 고름
  → 코드가 43개 읍면동 전체를 계산·판정 → 진단 카드·그래프·쉬운 말 요약·데이터 지도.
- 모든 수치는 코드가 계산하고, 지표마다 허브 자료 번호·기준 시점을 붙인다.
"""
from __future__ import annotations

import html as _html
import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from agent import llm
from graph import access as da
from graph import charts
from graph import engine as en
from graph import pipeline as pp
from graph.interpret import interpret, normalize_place
from tools import data_map
from tools.theme import CSS, badge, esc

ROOT = Path(__file__).resolve().parent
EXAMPLES = ["애월에 카페가 너무 많을까요? 한림보다 경쟁이 심한지 궁금해요.",
            "한림읍 편의점은 몇 개야?",
            "2026년 8월 노형동과 연동의 방문객 비교해줘",
            "성산에 게스트하우스 많아?",
            "애월 방문객이 요즘 늘고 있어?"]
PLOTLY_CFG = {"displaylogo": False, "displayModeBar": False}
RESTRICTED = re.compile(r"카드|매출|POS|유동인구|통신|와이파이|결제|내비")

st.set_page_config(page_title="제주 데이터 상담 에이전트", page_icon="🍊", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
ss = st.session_state
ss.setdefault("res", None)
ss.setdefault("ask", None)
ss.setdefault("pending", None)


# ---------------- 조각 ----------------

def section(title: str):
    st.markdown(f'<div class="jj-section">{esc(title)}</div>', unsafe_allow_html=True)


def kpi(label: str, value, unit: str = "") -> str:
    return f'<div class="jj-kpi"><div class="k">{esc(label)}</div><div class="v">{esc(value)}<small>{esc(unit)}</small></div></div>'


def hero():
    g = en.kg()
    n_ds = sum(1 for v in g.n.values() if v["type"] == "Dataset")
    st.markdown(f"""
<div class="jj-hero">
  <div class="eyebrow">제주빅데이터센터 · 도민 데이터 상담 (통합 버전)</div>
  <h1>제주 데이터 상담 에이전트</h1>
  <p>말로 물으면 지식 그래프가 제주데이터허브 자료 중 필요한 것을 골라, 실제 데이터로 계산한 진단표와 근거를 보여 드립니다.</p>
  <span class="jj-chip">지식 그래프 <b>허브 {n_ds:,}종</b></span>
  <span class="jj-chip">읍면동 <b>43곳</b> 비교</span>
  <span class="jj-chip">모델 <b>{esc(llm.model_name())}</b> · 로컬 실행 · LLM {esc(llm.llm_mode())}</span>
  <span class="jj-chip">오늘 허브 API <b>{da.calls_today()}/{da.DAILY_CALL_BUDGET}회</b></span>
</div>""", unsafe_allow_html=True)


def split_unit(text: str) -> tuple[str, str]:
    m = re.match(r"^([+\-]?[\d,]+(?:\.\d+)?)(.*)$", text)
    return (m.group(1), m.group(2)) if m else (text, "")


def src_text(m) -> str:
    return " · ".join(f"허브 {s['hub_id']} {s['title']} ({s['period']}, {s['via']})" for s in m.sources)


def indicator_card(r: dict, m) -> str:
    if r["판정"] == "확인 불가":
        val = '<div class="val na">확인 불가</div>'
        meta = f'<div class="note">사유: {esc(r["사유"])}</div>'
    elif r["판정"] == "제주 전체":
        num, unit = split_unit(pp.fmt(m.scalar, m.unit, m.digits))
        val = f'<div class="val">{esc(num)}<span class="unit">{esc(unit)}</span></div>'
        meta = f'<div class="meta">제주 전체 · 값이 있는 읍면동 {r["비교 수"]}곳</div>'
    else:
        num, unit = split_unit(pp.fmt(r["대상 값"], m.unit, m.digits))
        val = f'<div class="val">{esc(num)}<span class="unit">{esc(unit)}</span></div>'
        if r["순위"]:
            meta = (f'<div class="meta">제주 {r["비교 수"]}곳 중 <b>{r["순위"]}위</b> · 중앙값 '
                    f'{esc(pp.fmt(r["제주 중앙값"], m.unit, m.digits))}</div>')
        else:
            meta = f'<div class="meta">{esc(r.get("사유") or "비교 지역 부족으로 순위 없음")}</div>'
    label = "참고" if r["판정"] in ("참고", "제주 전체") else r["판정"]
    return (f'<div class="jj-card jj-ind"><div class="top"><span class="name">{esc(r["지표"])}</span>'
            f'{badge(label)}</div>{val}{meta}<div class="src">{esc(src_text(m) or "자료 없음")}</div></div>')


# ---------------- 실행 ----------------

def start(q: str):
    with st.spinner("질문을 읽고 있어요… (로컬 모델)"):
        slots, rec = interpret(q)
    ss["interp"] = rec
    if rec.get("ask"):
        ss["ask"], ss["pending"] = rec["ask"], (q, slots)
        ss["res"] = None
        return
    run(q, slots)


def run(q: str, slots: dict):
    with st.spinner("지식 그래프로 자료를 고르고 43개 읍면동을 계산하고 있어요… (처음 받는 자료는 1~2분 걸릴 수 있어요)"):
        res = pp.run(q, slots)
    rec = ss.get("interp") or {}
    res.log.insert(0, {"stage": "질문 해석", "by": rec.get("by", "모델"), "sec": rec.get("sec", 0),
                       "detail": f"모델 원문 {rec.get('raw')} → 사용 {slots}" + (f" / 가드: {'; '.join(rec['guards'])}" if rec.get("guards") else "")})
    ss["res"], ss["ask"], ss["pending"] = res, None, None


# ---------------- 결과 화면 ----------------

def show_result(res: pp.Result):
    area = res.places[0] if res.places else res.focus
    title = res.lens_title or "데이터로 본 답"
    where = ", ".join(res.places) if res.places else (f"제주 전체 (카드는 1위 {res.focus} 기준)" if res.focus else "제주 전체")
    section(f"{title} · {where}")
    st.markdown(f'<div class="jj-note"><b>{esc(res.lead)}</b></div>', unsafe_allow_html=True)
    if not res.metrics:
        for l in res.limits:
            st.caption(l)
        return
    cnt = pd.Series([r["판정"] for r in res.rows]).value_counts()
    k = st.columns(4)
    k[0].markdown(kpi("높음", int(cnt.get("높음", 0)), "개 지표"), unsafe_allow_html=True)
    k[1].markdown(kpi("보통", int(cnt.get("보통", 0)), "개 지표"), unsafe_allow_html=True)
    k[2].markdown(kpi("낮음", int(cnt.get("낮음", 0)), "개 지표"), unsafe_allow_html=True)
    k[3].markdown(kpi("참고·확인 불가", int(cnt.get("참고", 0) + cnt.get("확인 불가", 0) + cnt.get("제주 전체", 0)), "개"),
                  unsafe_allow_html=True)
    st.write("")
    byid = {m.id: m for m in res.metrics}
    for i in range(0, len(res.rows), 3):
        cols = st.columns(3)
        for c, r in zip(cols, res.rows[i:i + 3]):
            c.markdown(indicator_card(r, byid[r["id"]]), unsafe_allow_html=True)
        st.write("")
    st.caption("판정은 제주 읍면동 사이의 상대 위치(상위 25% 높음 · 하위 25% 낮음)이며, 좋고 나쁨이나 결정을 정해 주는 결과가 아닙니다.")

    section("근거 그래프")
    ok = [m for m in res.metrics if not m.reason]
    tabs, figs = [], []
    if area:
        f = charts.position_chart(ok, area, res.places[1:])
        if f:
            tabs.append("제주 안에서의 위치"); figs.append(f)
    if ok:
        f = charts.rank_chart(ok[0], res.places)
        if f:
            tabs.append("읍면동 순위"); figs.append(f)
    for m in ok:
        f = charts.trend_chart(m, area) if area else None
        if f:
            tabs.append("월별 추이"); figs.append(f)
            break
    if tabs:
        for t, f in zip(st.tabs(tabs), figs):
            with t:
                st.plotly_chart(f, use_container_width=True, config=PLOTLY_CFG)
    else:
        st.caption("비교할 읍면동 값이 부족해 그래프를 그리지 않았습니다.")
    if len(res.places) > 1:
        tb = pd.DataFrame({m.name: [pp.fmt(m.values.get(p), m.unit, m.digits) for p in res.places] for m in ok}, index=res.places)
        st.dataframe(tb, use_container_width=True)

    section("쉬운 말 요약")
    st.markdown('<div class="jj-card">' + "".join(f"<p>• {esc(x)}</p>" for x in res.sentences) + "</div>", unsafe_allow_html=True)

    section("이 답변의 데이터 지도")
    pri = lambda w: 0 if any(k in w for k in ("결합", "측정 범위", "센터 서버", "기간")) else 1
    cand = dict(sorted(res.rejected.items(), key=lambda kv: pri(kv[1]))[:5])
    joins = []
    for m in res.metrics:
        if len(m.measures) == 2 and m.joinable:
            ov = (m.joinable.get("overlap") or [""])[0][:7]
            joins.append((m.measures[0].dataset, m.measures[1].dataset, f"결합 {m.joinable.get('space_key')} · {ov}~".strip(" ·~")))
    data_map.show_answer(res.used, res.places, candidates=cand, joins=joins)
    st.caption("주황 원은 이번 답변에 쓴 자료, 회색 원은 지식 그래프가 검토했지만 쓰지 않은 자료(누르면 사유), 주황 선은 같은 지역 단위·겹치는 기간으로 결합할 수 있는 관계입니다.")

    with st.expander("계산 방법과 한계"):
        rows = []
        for m in res.metrics:
            for x in m.measures:
                rows.append({"지표": m.name, "허브 자료": f"{x.dataset} {x.title}", "가져온 방식": x.via,
                             "계산": {"count": "행 수", "sum": "합계", "mean": "평균", "daily_mean": "날짜별 합계의 평균(일평균)"}[x.op],
                             "컬럼": x.column or "-", "지역 컬럼": f"{x.place_column}({x.place_grain})",
                             "필터": ", ".join(f"{k}={'·'.join(map(str, v))}" for k, v in x.filters.items()) or "-",
                             "기준 시점": m.period})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        for l in res.limits:
            st.markdown(f"- {esc(l)}")
    with st.expander("분석 과정 기록 (단계·담당·소요 시간·토큰)"):
        st.dataframe(pd.DataFrame([{"단계": r["stage"], "담당": r["by"], "초": r.get("sec"),
                                    "토큰(입력/출력)": f"{r.get('prompt_eval_count')}/{r.get('eval_count')}" if r.get("eval_count") else "",
                                    "내용": r["detail"]} for r in res.log]), hide_index=True, use_container_width=True)
    show_export(res)


def report_html(res: pp.Result) -> str:
    rows = "".join(f"<tr><td>{_html.escape(r['지표'])}</td><td>{_html.escape(pp.fmt(r['대상 값'] if r['대상 값'] is not None else r.get('제주 전체'), m.unit, m.digits))}</td>"
                   f"<td>{_html.escape(str(r['판정']))}</td><td>{r['순위'] or '-'}</td><td>{_html.escape(src_text(m))}</td></tr>"
                   for r, m in zip(res.rows, res.metrics))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>제주 데이터 상담 결과</title>
<style>body{{font-family:'Pretendard GOV','Noto Sans KR','Malgun Gothic',sans-serif;max-width:900px;margin:30px auto;color:#1F2933}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #E2E7ED;padding:6px 8px;font-size:14px}}th{{background:#F5F7F9}}</style></head>
<body><h2>{_html.escape(res.lens_title or '데이터로 본 답')}</h2><p><b>질문</b> {_html.escape(res.question)}</p>
<p><b>{_html.escape(res.lead)}</b></p><table><tr><th>지표</th><th>값</th><th>판정</th><th>순위</th><th>자료</th></tr>{rows}</table>
<h3>요약</h3><ul>{''.join(f'<li>{_html.escape(s)}</li>' for s in res.sentences)}</ul>
<h3>한계</h3><ul>{''.join(f'<li>{_html.escape(s)}</li>' for s in res.limits)}</ul>
<p style="color:#6B7685">모든 수치는 제주데이터허브 원자료에서 코드로 계산했습니다. 판정은 제주 읍면동 사이 상대 위치입니다.</p></body></html>"""


def show_export(res: pp.Result):
    section("반출 점검")
    restricted = any(RESTRICTED.search(s["title"]) for m in res.metrics for s in m.sources)
    small = any(m.measures and m.measures[0].op == "count" and (m.values.dropna() < 10).any() for m in res.metrics if not m.reason)
    items = [
        ("결과 리포트(HTML)", "응용집계·문장", "가능", "집계 결과와 출처만 담음(원본 행·상호·주소 없음)"),
        ("읍면동별 결과 표(CSV)", "단순·응용집계",
         "조건부" if (restricted or small) else "가능",
         ("제한 데이터군(카드·유동인구 등) 기반 표는 운영자 확인 필요" if restricted else "")
         + (" · 10 미만 값은 '10 미만'으로 처리" if small else "") or "공개 데이터 집계"),
        ("원본 데이터", "원본", "불가" if restricted else "조건부", "원본은 센터 반출 절차를 따름"),
    ]
    st.markdown("".join(f'<div class="jj-card" style="margin-bottom:6px">{badge(p)} <b>{esc(n)}</b> · {esc(k)} — '
                        f'<span style="color:#6B7685">{esc(w)}</span></div>' for n, k, p, w in items), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.download_button("결과 리포트 내려받기(HTML)", report_html(res).encode("utf-8"), "제주데이터상담_결과.html", "text/html")
    tb = pd.DataFrame({m.name: m.values for m in res.metrics if not m.reason})
    if not tb.empty:
        tb = tb.map(lambda v: "10 미만" if isinstance(v, float) and 0 < v < 10 and small else v)
        buf = io.StringIO()
        tb.to_csv(buf, encoding="utf-8")
        c2.download_button("읍면동별 결과 표(CSV)", buf.getvalue().encode("utf-8-sig"), "읍면동별_결과.csv", "text/csv",
                           disabled=restricted, help="제한 데이터군 기반 표는 운영자 확인 후 반출합니다." if restricted else None)


# ---------------- 본문 ----------------

hero()
left, main = st.columns([1, 2.4], gap="large")
with left:
    section("질문")
    with st.form("q", clear_on_submit=False):
        q = st.text_area("제주에 대해 궁금한 것을 평소 말로 적어 주세요", height=110,
                         placeholder="예) 애월에 카페가 너무 많을까요?")
        go_ = st.form_submit_button("분석 시작", type="primary", use_container_width=True)
    notice = st.container()  # 안내·되묻기는 질문 칸 바로 아래(예시 질문 위)에 보여 준다
    st.caption("예시 질문")
    for i, ex in enumerate(EXAMPLES):
        if st.button(ex, key=f"ex{i}", use_container_width=True):
            start(ex)
    if go_ and q.strip():
        start(q.strip())
    if ss.get("ask"):
        with notice:
            st.warning(ss["ask"])
            qq, slots = ss["pending"]
            names = re.findall(r"'([^']+)'", ss["ask"])
            target = names[1] if len(names) >= 2 else (names[0] if names else None)
            adm = normalize_place(target)[0] if target else None
            if adm and slots.get("concepts"):
                b1, b2 = st.columns(2)
                if b1.button(f"네, {adm}", use_container_width=True):
                    slots["places"] = [adm] + [p for p in slots["places"] if p != adm]
                    run(qq, slots)
                    st.rerun()
                if b2.button("아니요", use_container_width=True):
                    run(qq, slots)
                    st.rerun()
            raw = (ss.get("interp") or {}).get("raw")
            if raw is not None:
                with st.expander("모델 해석 원문(JSON)"):
                    st.json(raw)

with main:
    if ss.get("res"):
        show_result(ss["res"])
    else:
        section("이렇게 답해 드려요")
        st.markdown(
            '<div class="jj-card"><p>① 질문을 로컬 모델이 정해진 어휘(검수 개념 162개)로 해석합니다.</p>'
            '<p>② 지식 그래프가 허브 자료 중 필요한 자료와 함께 쓸 수 있는 조합(같은 지역 단위·겹치는 기간)을 고릅니다.</p>'
            '<p>③ 코드가 제주 43개 읍면동 전체를 계산해 상대 위치(높음·보통·낮음)를 판정합니다. 숫자는 모델이 만들지 않습니다.</p>'
            '<p>④ 진단 카드·그래프·쉬운 말 요약과 함께, 이번 답변에 쓴 자료를 데이터 지도로 보여 드립니다.</p></div>',
            unsafe_allow_html=True)
        section("제주 데이터 지도")
        data_map.show_home(height=560)
        st.caption("지식 그래프에 연결된 제주데이터허브 자료 지도입니다. 진한 남색은 분야, 파란 원은 자료, 연한 원은 자료로 알 수 있는 것과 지역 단위입니다. 자료를 누르면 설명과 허브 링크가 나옵니다.")
        section("제주 데이터 지도 (이전 방식: 대표 자료 20개)")
        data_map.show_home_classic(height=520)
        st.caption("시안 비교용: 대표 자료 20개로 시작하고, 분야·개념 원을 누르면 관련 자료가 6개씩 펼쳐집니다.")
        section("제주 데이터 지도 (합친 방식: 대표 20개 + 검색·분야 버튼)")
        data_map.show_home_hybrid(height=560)
        st.caption("시안 비교용: 이전 방식의 보기를 기본으로, 검색창과 분야 버튼을 붙였습니다. 결과는 20개씩 보여 주고 '더 보기'로 늘립니다.")
