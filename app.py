"""JEJU:ON(제주온) · 제주 데이터 동네상담소 — 화면 (B 화면 디자인 + A 지식 그래프 데이터 선별).

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
from graph import interpret as it
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

st.set_page_config(page_title="JEJU:ON · 제주 데이터 동네상담소", page_icon="🍊", layout="wide")
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


LOGO_SVG = ('<svg width="44" height="44" viewBox="0 0 44 44" aria-hidden="true"><rect width="44" height="44" rx="13" fill="#124454"/>'
            '<path d="m5 27 12-10 4 3 6-10 12 17-15 6z" fill="#a9ede1"/><path d="m5 27 16-4 7-6 11 10-15 6z" fill="#38a69e"/>'
            '<path d="m9 30 15 5 12-4" fill="none" stroke="#fff" stroke-width="1.5"/></svg>')  # JEJU:ON 로고(jeju-agent 서비스)


def hero():
    g = en.kg()
    n_ds = sum(1 for v in g.n.values() if v["type"] == "Dataset")
    st.markdown(f"""
<div class="jj-hero">
  <div class="eyebrow">제주빅데이터센터 · 도민 데이터 상담</div>
  <div class="jj-brand"><span class="logo">{LOGO_SVG}</span><b>JEJU<span>:ON</span></b><i></i><em>제주 데이터 동네상담소</em></div>
  <h1>우리 동네 궁금한 거, 말로 물어봅서.</h1>
  <p>지식 그래프가 제주데이터허브 자료 {n_ds:,}종 중 필요한 것을 골라, 43개 읍면동을 직접 계산해 근거와 함께 보여 드립니다.</p>
</div>""", unsafe_allow_html=True)


def dev_footer():
    """개발용 상태(모델 켜짐 여부, 오늘 허브 API 사용량)는 화면 맨 아래에 작게."""
    st.markdown("---")
    st.caption(f"JEJU:ON · 제주 데이터 동네상담소 — 모델 {llm.model_name()} (LLM {llm.llm_mode()}) · "
               f"오늘 허브 API {da.calls_today()}/{da.DAILY_CALL_BUDGET}회 · 해석 재점검 {'켬' if it.review_on() else '끔'}")


def split_unit(text: str) -> tuple[str, str]:
    if re.search(r"\d[억만]", text):  # '1억 8,628만 원' → ('1억 8,628만', ' 원')
        head, _, unit = text.rpartition(" ")
        return head, " " + unit
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
    rv = rec.get("review") or {}
    detail = f"모델 원문 {rec.get('raw')}"
    if rv:
        detail += (f" → 재점검 {rec.get('raw_review')} (고친 항목: {', '.join(rv.get('changed') or []) or '없음'}, {rv.get('sec')}초)"
                   if rv.get("ok") else " → 재점검 실패(1차 해석 사용)")
    detail += f" → 사용 {slots}" + (f" / 가드: {'; '.join(rec['guards'])}" if rec.get("guards") else "")
    res.log.insert(0, {"stage": "질문 해석", "by": rec.get("by", "모델"), "sec": rec.get("sec", 0), "detail": detail})
    ss["res"], ss["ask"], ss["pending"] = res, None, None


# ---------------- 해석 확인·고치기 ----------------

ANALYSIS_KO = {"count": "개수", "sum": "합계", "mean": "평균", "ratio": "밀도·비율", "compare": "지역 비교", "trend": "변화(추이)",
               "share": "구성비", "rank": "순위(어디가)", "lookup": "값 조회"}
WANT_KO = {"high": "많은·높은 곳", "low": "적은·낮은 곳"}


def interp_line(s: dict) -> str:
    """모델이 이해한 내용을 한 줄로(빠진 항목은 '없음'으로 보여 사용자가 알아채게 한다)."""
    chips = [("지역", ", ".join(s.get("places") or []) or "제주 전체"),
             ("무엇을", ", ".join(pp.label(c) for c in s.get("concepts") or []) or "없음"),
             ("나누는 기준", ", ".join(f"{k}={v}" for k, v in (s.get("filters") or {}).items()) or "없음"),
             ("분석", ANALYSIS_KO.get(s.get("analysis"), s.get("analysis") or "-")),
             ("기간", f"{s['period'][0]}~{s['period'][1]}" if s.get("period") else "최신 자료"),
             ("조건 방향", ", ".join(f"{pp.label(g['concept'])} {WANT_KO[g['want']]}" for g in (s.get("goal") or [])) or "없음")]
    if s.get("ratio"):
        r = s["ratio"]
        chips.append(("비율", f"{pp.label(r['numerator'])} ÷ {pp.label(r['denominator'])}"))
    return "".join(f'<span class="jj-chip2"><b>{esc(k)}</b> {esc(v)}</span>' for k, v in chips)


def interp_editor(res: pp.Result):
    s = res.slots
    V = it.vocab()
    with st.expander("해석 고치기 — 빠졌거나 틀린 조건이 있으면 바꾸고 다시 계산하세요"):
        with st.form("fix_interp"):
            c1, c2 = st.columns(2)
            places = c1.multiselect("지역(비우면 제주 전체)", sorted(it._regions()), default=[p for p in s.get("places") or [] if p in it._regions()],
                                    max_selections=4)
            concepts = c2.multiselect("무엇을(측정값, 3개까지)", V["measures"], default=[c for c in s.get("concepts") or [] if c in V["measures"]],
                                      max_selections=3, format_func=pp.label)
            f0 = next(iter((s.get("filters") or {}).items()), (None, ""))
            c3, c4, c5 = st.columns([1, 1, 1])
            dims = ["(없음)"] + V["dims"]
            dim = c3.selectbox("나누는 기준", dims, index=dims.index(f0[0]) if f0[0] in dims else (dims.index("업종") if "업종" in dims else 0))
            val = c4.text_input("기준 값(예: 한식, 카페)", value=str(f0[1] or ""))
            keys = list(ANALYSIS_KO)
            ana = c5.selectbox("분석", keys, index=keys.index(s.get("analysis")) if s.get("analysis") in keys else keys.index("lookup"),
                               format_func=lambda k: ANALYSIS_KO[k])
            dens = st.checkbox("경쟁·밀집도로 계산(방문 1만당 점포 수)", value=bool(s.get("ratio")))
            c6, c7 = st.columns(2)
            p0 = c6.text_input("기간 시작(YYYY-MM-DD, 비우면 최신)", value=s["period"][0] if s.get("period") else "")
            p1 = c7.text_input("기간 끝", value=s["period"][1] if s.get("period") else "")
            st.caption("조건 방향(두 조건을 함께 보는 질문): 예) 외국인방문인구 많은 곳 + 점포수 적은 곳")
            goals = list(s.get("goal") or [])
            gs = []
            for i in range(2):
                g = goals[i] if i < len(goals) else {}
                a, b = st.columns([2, 1])
                opts = ["(없음)"] + V["measures"]
                gc = a.selectbox(f"조건 {i + 1}", opts, index=opts.index(g["concept"]) if g.get("concept") in opts else 0, key=f"gc{i}",
                                 format_func=pp.label)
                gw = b.selectbox("방향", ["high", "low"], index=0 if g.get("want", "high") == "high" else 1,
                                 format_func=lambda w: WANT_KO[w], key=f"gw{i}")
                if gc != "(없음)":
                    gs.append({"concept": gc, "want": gw})
            go_ = st.form_submit_button("이 해석으로 다시 계산", type="primary")
        if go_:
            new = dict(s)
            new["places"] = places
            new["concepts"] = list(dict.fromkeys(concepts + [g["concept"] for g in gs]))[:3]
            if dens and "점포수" not in new["concepts"]:
                new["concepts"] = (["점포수"] + new["concepts"])[:3]
            new["filters"] = {dim: val.strip()} if dim != "(없음)" and val.strip() else {}
            new["analysis"] = "ratio" if dens and ana in ("lookup", "count") else ana
            new["ratio"] = {"numerator": "점포수", "denominator": "방문인구", "scale": 10000} if dens else None
            new["period"] = (p0.strip(), p1.strip()) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p0.strip()) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p1.strip()) else None
            new["goal"] = gs
            rec = ss.get("interp") or {}
            rec["guards"] = list(rec.get("guards") or []) + ["사용자가 해석을 고침"]
            rec["removed"] = []
            ss["interp"] = rec
            run(res.question, new)
            st.rerun()


# ---------------- 결과 화면 ----------------

def show_result(res: pp.Result):
    area = res.places[0] if res.places else res.focus
    title = res.lens_title or "데이터로 본 답"
    where = ", ".join(res.places) if res.places else "제주 전체"
    section(f"{title} · {where}")
    # 0) 모델이 이해한 내용(빠진 조건을 사용자가 바로 보고 고칠 수 있게)
    st.markdown(f'<div class="jj-interp"><span class="t">이렇게 이해했어요</span>{interp_line(res.slots)}</div>', unsafe_allow_html=True)
    interp_editor(res)
    # 1) 답 카드: 결론 한 줄 + 해설(일상 말 ↔ 자료 뜻) + 오래된 자료 경고
    notes = "".join(f'<div class="n">{esc(n)}</div>' for n in res.notes_top)
    warns = "".join(f'<div class="w">{esc(w)}</div>' for w in res.warnings)
    st.markdown(f'<div class="jj-answer"><div class="a">{esc(res.lead)}</div>{notes}{warns}</div>', unsafe_allow_html=True)
    if not res.metrics:
        for l in res.limits:
            st.caption(l)
        return
    byid = {m.id: m for m in res.metrics}
    asked_rows = [r for r in res.rows if getattr(byid[r["id"]], "asked", False)]
    lens_rows = [r for r in res.rows if r not in asked_rows]
    if not asked_rows:
        asked_rows, lens_rows = res.rows[:1], res.rows[1:]

    # 2) 질문 지표 카드(크게). 지역 없는 질문은 1위 지역 값을 보여 준다는 것을 분명히 적는다
    if not res.places and res.focus:
        m_top = byid[asked_rows[0]["id"]]
        st.markdown(f'<div class="jj-why">지역을 정하지 않은 질문이라, 카드는 <b>{esc(m_top.name)} 제주 1위인 {esc(res.focus)}</b>의 값입니다.</div>',
                    unsafe_allow_html=True)
    cols = st.columns(min(len(asked_rows), 3))
    for c, r in zip(cols, asked_rows[:3]):
        c.markdown(indicator_card(r, byid[r["id"]]), unsafe_allow_html=True)
    st.write("")

    # 3) 근거 그래프(코드 규칙으로 고름)
    section("근거 그래프")
    picks = charts.choose_charts(res, res.slots)
    if picks:
        for tab, (name, fig, why) in zip(st.tabs([p[0] for p in picks]), picks):
            with tab:
                st.markdown(f'<div class="jj-why">{esc(why)}</div>', unsafe_allow_html=True)
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    else:
        st.caption("비교할 읍면동 값이 부족해 그래프를 그리지 않았습니다.")
    if res.cross:
        st.caption(f"조건 교차표 — 가로: {res.cross['b_name']}(중앙값 기준), 세로: {res.cross['a_name']}(상·하위 25%), 칸 = 읍면동 수")
        st.dataframe(res.cross["table"], use_container_width=True)
    ok = [m for m in res.metrics if not m.reason]
    if len(res.places) > 1 and ok:
        tb = pd.DataFrame({m.name: [pp.fmt(m.values.get(p), m.unit, m.digits) for p in res.places] for m in ok}, index=res.places)
        st.dataframe(tb, use_container_width=True)

    # 4) 함께 보면 좋은 지표(관점 지표, 기본 닫힘)
    if lens_rows:
        with st.expander(f"{res.lens_title or '관련'} 관점에서 함께 볼 지표 {len(lens_rows)}개"):
            for i in range(0, len(lens_rows), 3):
                cs = st.columns(3)
                for c, r in zip(cs, lens_rows[i:i + 3]):
                    c.markdown(indicator_card(r, byid[r["id"]]), unsafe_allow_html=True)
                st.write("")
    st.caption("판정은 제주 읍면동 사이의 상대 위치(상위 25% 높음 · 하위 25% 낮음)이며, 좋고 나쁨이나 결정을 정해 주는 결과가 아닙니다.")

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
    st.caption("※ 허브에 있는 관측 자료(과거·현재)로만 답합니다. 내년·앞으로 같은 미래 예측이나 순이익처럼 자료에 없는 값은 답해 드리기 어렵습니다.")
    notice = st.container()  # 안내·되묻기는 질문 칸 바로 아래(예시 질문 위)에 보여 준다
    st.caption("예시 질문")
    for i, ex in enumerate(EXAMPLES):
        if st.button(ex, key=f"ex{i}", use_container_width=True):
            start(ex)
    if go_ and q.strip():
        start(q.strip())
    removed = (ss.get("interp") or {}).get("removed") or []
    if ss.get("res") and not ss.get("ask") and removed:
        with notice:
            st.info("질문에 근거가 없어 빼고 계산한 값: " + " · ".join(removed)
                    + ". 필요하면 결과 위 '해석 고치기'에서 넣고 다시 계산해 주세요.")
    if ss.get("ask"):
        with notice:
            st.warning(ss["ask"])
            qq, slots = ss["pending"]
            choices = (ss.get("interp") or {}).get("choices") or []
            if choices and slots.get("concepts"):
                bs = st.columns(len(choices))
                for b, ch in zip(bs, choices):
                    if b.button(ch["label"], use_container_width=True, key=f"choice_{ch['label']}"):
                        slots["places"] = list(ch["places"])
                        if len(ch["places"]) > 1 and slots.get("analysis") not in ("trend", "rank", "ratio"):
                            slots["analysis"] = "compare"  # 사용자가 '둘 다 비교'를 눌렀을 때만
                        ss["interp"]["guards"] = ss["interp"].get("guards", []) + [f"사용자 선택: {ch['label']}"]
                        run(qq, slots)
                        st.rerun()
            names = re.findall(r"'([^']+)'", ss["ask"])
            target = names[1] if len(names) >= 2 else (names[0] if names else None)
            adm = normalize_place(target)[0] if target and not choices else None
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

dev_footer()
