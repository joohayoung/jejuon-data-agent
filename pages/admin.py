"""운영자 화면 (/admin) — 도민이 낸 반출 신청을 점검한다. (팀원 jeju-analyst-poc의 pages/admin.py를 옮김)

도민 화면(/)과 주소로 나뉜다. 운영자는 도민의 질문, 조회한 데이터, 반출을 바라는 원문 데이터를 보고
데이터마다 동의(체크)·제외(체크 해제 + 사유, 기본 사유는 보안)를 정한 뒤 '반출 점검 완료'를 누른다.
접근 코드는 .env의 ADMIN_CODE(없으면 시연용으로 코드 없이 열림).
"""
from __future__ import annotations


import pandas as pd
import streamlit as st

from tools import admin_report, data_export, export_check, export_flow
from tools.theme import CSS, badge, esc

st.set_page_config(page_title="JEJU:ON 운영자 · 반출 점검", page_icon="🛡", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS + """<style>[data-testid="stSidebarNav"]{display:none}
.jj-admin{background:linear-gradient(120deg,#2B2F36,#3E4650);color:#fff;border-radius:18px;padding:22px 28px;margin-bottom:14px}
.jj-admin h1{color:#fff;margin:0 0 4px;font-size:1.7rem}.jj-admin p{margin:0;color:#D5DAE0}</style>""",
            unsafe_allow_html=True)
ss = st.session_state


def section(t: str):
    st.markdown(f'<div class="jj-section">{esc(t)}</div>', unsafe_allow_html=True)


STATUS_ICON = {"대기": "🟡 대기", "승인": "🟢 승인", "부분승인": "🟠 부분승인", "반려": "🔴 반려"}

st.markdown("""<div class="jj-admin"><h1>🛡 운영자 · 반출 점검</h1>
<p>도민이 낸 질문과 조회한 데이터를 확인하고, 반출할 허브 원문 데이터를 데이터마다 동의하거나 제외합니다.
(센터 반출 기준 적용 예시 · 허브 공개 데이터)</p></div>""", unsafe_allow_html=True)
try:
    st.page_link("app.py", label="← 도민 화면으로", icon="🍊")
except Exception:  # 운영자 화면만 단독 실행할 때(시험 등)
    pass

code = export_flow.admin_code()
if code and not ss.get("admin_ok"):
    typed = st.text_input("운영자 코드", type="password")
    if typed and typed == code:
        ss["admin_ok"] = True
        st.rerun()
    elif typed:
        st.error("코드가 맞지 않습니다.")
    st.stop()
if not code:
    st.caption("시연 모드: 운영자 코드가 설정되지 않아(.env ADMIN_CODE) 누구나 이 주소로 들어올 수 있습니다. "
               "실제 운영에서는 코드·접근 제한이 필요합니다.")

tab_req, tab_rule, tab_ops = st.tabs(["반출 점검", "반출 점검 기준·대상 목록", "운영 현황"])

# ------------------------------------------------------------ 반출 점검
with tab_req:
    recs = export_flow.list_all()
    k = st.columns(4)
    for col, (lab, val) in zip(k, [("전체 신청", len(recs)), ("점검 대기", sum(r["status"] == "대기" for r in recs)),
                                   ("승인·부분승인", sum(r["status"] in ("승인", "부분승인") for r in recs)),
                                   ("반려", sum(r["status"] == "반려" for r in recs))]):
        col.markdown(f'<div class="jj-kpi"><div class="k">{lab}</div><div class="v">{val}<small>건</small></div></div>',
                     unsafe_allow_html=True)
    st.write("")
    if recs:
        if st.button("📄 전체 반출 기록 보고서(PDF) 만들기"):
            with st.spinner("PDF를 만들고 있어요…"):
                ss["admin_pdf_all"] = admin_report.build_pdf(recs)
        if ss.get("admin_pdf_all"):
            st.download_button("⬇ 전체 반출 기록 보고서 내려받기", ss["admin_pdf_all"], file_name="반출_점검_기록_전체.pdf",
                               mime="application/pdf")
        st.write("")
    if not recs:
        st.markdown('<div class="jj-note">아직 도민이 낸 반출 신청이 없습니다. 도민 화면에서 질문한 뒤 답에 쓴 데이터의 '
                    '‘데이터 반출 신청’을 하면 여기에 나타납니다.</div>', unsafe_allow_html=True)
    else:
        labels = {r["id"]: f"{STATUS_ICON[r['status']]} · {r['created_at'][5:16].replace('T', ' ')} · "
                           + ("데이터 반출 · " if r.get("kind") == "data" else f"{(r['area'] or '')} {(r['industry'] or '')} · ")
                           + r["id"] for r in recs}
        pick = st.selectbox("신청 목록 (최신순)", list(labels), format_func=labels.get)
        rec = export_flow.load(pick)
        pending = rec["status"] == "대기"

        section("1. 도민이 한 질문과 신청")
        st.markdown(f"**{esc(rec['question'])}**")
        for f in rec["followups"]:
            st.markdown(f"· 이어서: {esc(f)}")
        st.caption(f"신청 번호 {rec['id']} · 신청 {rec['created_at']} · 활용 목적: {rec['purpose']}")

        section("2. 분석하며 조회한 데이터" if rec.get("kind") != "data" else "2. 신청한 데이터(데이터군·수록 기간)")
        st.dataframe(pd.DataFrame([{"데이터(기준 시점)": d["data"], "데이터군": d["group"],
                                    "반출 점검": "대상 아님(외부 데이터, 사용 사실만 표시)" if d["external"] else "대상"}
                                   for d in rec["datasets"]]), hide_index=True, use_container_width=True)

        section("3. 신청한 원문 데이터 — 어디까지 동의할까요?")
        st.caption("체크 = 반출에 동의. 체크를 끄면 그 데이터만 빼고 반출하며, 제외 사유를 적습니다(기본: 보안상). "
                   "정책상 ‘불가’ 판정은 동의할 수 없고 자동으로 제외됩니다.")
        choices = {}
        for i, it in enumerate(rec["items"]):
            with st.container(border=True):
                a, b = st.columns([3, 1.4])
                if it["locked"]:
                    a.checkbox(it["name"], value=False, disabled=True, key=f"{rec['id']}_c{i}")
                    ok = False
                elif pending:
                    ok = a.checkbox(it["name"], value=True, key=f"{rec['id']}_c{i}")
                else:
                    ok = it["decision"] == "동의"
                    a.checkbox(it["name"], value=ok, disabled=True, key=f"{rec['id']}_c{i}")
                b.markdown(badge(it["사전 판정"]), unsafe_allow_html=True)
                hid = data_export.hub_id_of(it)
                if hid:
                    a.markdown(f"[제주데이터허브 {hid}번 원문 페이지]({data_export.HUB_VIEW_URL.format(hub_id=hid)})")
                a.caption(f"{it['집계 유형']} · {', '.join(it['데이터군'])} · 처리: {', '.join(it['처리'])}"
                          + (f" · 범위: {it['scope']}" if it.get("scope") else ""))
                if it.get("보유"):
                    a.caption(("🟢 " if it.get("보유 여부") == "local" else "🔵 ") + it["보유"])
                if it.get("예외 필요"):
                    a.markdown(f"**예외 사유(도민 작성)**: {esc(it.get('예외 사유') or '없음')}", unsafe_allow_html=True)
                for why in it["사전 이유"]:
                    a.caption(f"· {why}")
                reason = ""
                if it["locked"] or (not pending and it["decision"] == "제외"):
                    st.markdown(f'<div class="jj-warn">제외: {esc(it["exclude_reason"])}</div>', unsafe_allow_html=True)
                elif pending and not ok:
                    reason = st.text_input("제외 사유", value=export_flow.DEFAULT_REASON, key=f"{rec['id']}_r{i}")
                choices[it["file"]] = {"approve": ok, "reason": reason}

        n_ok = sum(c["approve"] for c in choices.values())
        if pending:
            note = st.text_input("운영자 메모(선택, 도민에게도 보임)", key=f"{rec['id']}_note")
            result = "승인" if n_ok == len(rec["items"]) else ("반려" if n_ok == 0 else "부분승인")
            st.markdown(f"**동의 {n_ok}건 / 전체 {len(rec['items'])}건** → 결과: {result}")
            if st.button("반출 점검 완료", type="primary"):
                export_flow.decide(rec["id"], choices, note)
                st.rerun()
        else:
            st.markdown(f'<div class="jj-note"><b>{STATUS_ICON[rec["status"]]}</b> · 점검 완료 {rec["decided_at"]}'
                        + (f" · 메모: {esc(rec['admin_note'])}" if rec["admin_note"] else "") + "</div>",
                        unsafe_allow_html=True)
        if st.button("📄 이 신청의 점검 기록(PDF) 만들기", key=f"{rec['id']}_pdfb"):
            with st.spinner("PDF를 만들고 있어요…"):
                ss[f"pdf_{rec['id']}"] = admin_report.build_pdf([rec], f"반출 점검 기록 — {rec['id']}")
        if ss.get(f"pdf_{rec['id']}"):
            st.download_button("⬇ 점검 기록 PDF 내려받기", ss[f"pdf_{rec['id']}"], file_name=f"반출점검기록_{rec['id']}.pdf",
                               mime="application/pdf", key=f"{rec['id']}_pdfd")

# ------------------------------------------------------------ 기준·대상 목록
with tab_rule:
    R = export_check.rules()
    section("반출 점검 대상")
    st.markdown("도민이 답에 쓴 **제주데이터허브 원문 데이터**를 데이터별로 신청합니다(반출 형태: 원본·발췌, 단순집계, 응용집계, 시각화). "
                "분석 결과 그림·표가 아니라 허브 원문이 대상이며, 승인되면 도민 화면에서 허브 해당 데이터 페이지로 연결됩니다.")
    st.caption("외부 데이터(주민등록 인구·기상청·특일·관광공사·상가 최신)는 반출 점검 대상이 아니며, 분석에 쓰였다는 사실만 표시합니다.")

    section("데이터군과 규칙")
    st.caption(f"제한 데이터군으로 보는 허브 자료: {', '.join(str(h) for h in sorted(data_export.RESTRICTED_HUB))}번, "
               "그 밖에 제공기관·자료 이름에 카드·유동인구·POS·매출 등이 든 자료. 나머지는 개방 데이터군으로 봅니다.")
    c1, c2 = st.columns(2)
    kinds = {"raw": "원본·발췌", "simple_aggregate": "단순집계", "applied_aggregate": "응용집계",
             "visualization": "시각화", "text_or_spreadsheet": "텍스트·엑셀"}
    for col, g in zip((c1, c2), ("restricted", "open")):
        gr = R["groups"][g]
        col.markdown(f"**{gr['label']}** — 제공기관: {', '.join(gr['providers'])}")
        col.dataframe(pd.DataFrame([{"형태": kinds[k], "판정": v} for k, v in gr["rules"].items()]),
                      hide_index=True, use_container_width=True)
    st.caption(f"규칙: {R['source']['title']}({R['source']['revised']} 개정), 원문 대조 {R['source'].get('verified_at')} 완료. "
               f"단순집계 {R['small_value_threshold']} 미만은 '{R['small_value_label']}'로 범주 처리.")
    for n in R["notes"]:
        st.caption("· " + n)
    files = export_check.project_code_files()
    hits = export_check.scan_code(files)
    st.markdown(f"**소스코드 데이터 샘플 출력 검사**: {len(files)}개 파일, 발견 {len(hits)}건 → {'불가' if hits else '가능'}")

# ------------------------------------------------------------ 운영 현황
with tab_ops:
    section("데이터 신선도")
    st.caption("서비스가 쓰는 허브 자료의 갱신 주기와 실제 최신 기준일의 차이")
    st.dataframe(pd.DataFrame(data_export.freshness()), hide_index=True, use_container_width=True)
    section("답하지 못한 질문")
    st.caption("자료가 없거나 예측처럼 데이터로 답할 수 없는 요구라 보류한 질문입니다. 어떤 자료를 더 연결할지 정할 때 참고합니다.")
    rows = export_flow.unanswered()
    if rows:
        st.dataframe(pd.DataFrame([{"일시": r["일시"], "질문": r["질문"], "사유": r["사유"]} for r in rows]),
                     hide_index=True, use_container_width=True)
    else:
        st.caption("기록 없음")
