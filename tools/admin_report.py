"""운영자 반출 점검 기록 보고서(PDF). plotly 표 + kaleido로 만들어 새 패키지 없이 PDF를 낸다."""
from __future__ import annotations

import datetime as dt

import plotly.graph_objects as go

from tools import data_export
from tools.theme import C, FONT

STATUS = {"대기": "점검 대기", "승인": "승인", "부분승인": "부분승인", "반려": "반려"}


def _rows(recs: list[dict]) -> list[list[str]]:
    rows = []
    for r in recs:
        for it in r["items"]:
            hid = data_export.hub_id_of(it) if r.get("kind") == "data" else None
            rows.append([
                r["id"], r["created_at"][:16].replace("T", " "), (r["question"] or "")[:60],
                (f"[허브 {hid}] " if hid else "") + it["name"][:70],
                it.get("scope") or "-", it.get("사전 판정", "-"),
                it["decision"] or "점검 중", it.get("exclude_reason") or "-",
                (r["decided_at"] or "-")[:16].replace("T", " "), r.get("admin_note") or "-"])
    return rows


def build_pdf(recs: list[dict], title: str = "데이터 반출 점검 기록 보고서") -> bytes:
    rows = _rows(recs)
    cnt = {k: sum(r["status"] == k for r in recs) for k in STATUS}
    sub = (f"출력 {dt.datetime.now():%Y-%m-%d %H:%M} · 신청 {len(recs)}건(" + ", ".join(f"{STATUS[k]} {v}" for k, v in cnt.items())
           + ") · 센터 반출 기준 적용 예시(허브 공개 데이터)")
    head = ["신청 번호", "신청 일시", "질문·신청 내용", "데이터·반출 형태·형식", "범위", "사전 판정", "운영자 결정", "제외 사유", "점검 일시", "메모"]
    cols = list(zip(*rows)) if rows else [[] for _ in head]
    fig = go.Figure(go.Table(
        columnwidth=[150, 100, 200, 260, 120, 70, 80, 150, 100, 110],
        header=dict(values=[f"<b>{h}</b>" for h in head], fill_color=C["sea_soft"], line_color=C["line"], align="left",
                    font=dict(family=FONT, size=12, color=C["basalt"]), height=30),
        cells=dict(values=[list(c) for c in cols], align="left", line_color=C["line"], fill_color="#FFFFFF", height=34,
                   font=dict(family=FONT, size=11, color=C["basalt"]))))
    fig.update_layout(title=dict(text=f"<b>{title}</b><br><sup>{sub}</sup>", font=dict(size=18, color=C["basalt"]), x=0.01),
                      font=dict(family=FONT), width=1400, height=140 + 40 * max(len(rows), 1) + 30,
                      margin=dict(l=10, r=10, t=90, b=20), paper_bgcolor="#FFFFFF")
    last = None
    for attempt in range(3):
        try:
            return fig.to_image(format="pdf", width=1400)
        except Exception as e:  # kaleido가 가끔 브라우저 시작에 실패함
            last = e
    raise RuntimeError(f"PDF 생성 실패: {last}")
