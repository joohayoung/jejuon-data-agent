"""그래프(plotly, B 디자인 기준 tools/theme.py)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from graph.pipeline import fmt
from tools.theme import C, plotly_layout


def _u(m) -> str:
    """막대 라벨용 단위: '곳(방문 1만당)' → '곳'(뜻은 그래프 제목에 있음)."""
    u = m.unit or ""
    return u.split("(")[0] if "(" in u and not u.startswith("(") else u


def position_chart(metrics, target: str | None, compare: list[str]) -> go.Figure | None:
    """지표별 제주 읍면동 분포 위에 대상·비교 지역 위치."""
    items = [m for m in metrics if not m.reason and m.values.notna().sum() >= 2]
    if not items:
        return None
    fig = make_subplots(rows=len(items), cols=1, vertical_spacing=0.12,
                        subplot_titles=[f"<b>{m.name}</b>  <span style='color:{C['ink3']}'>{m.period}</span>" for m in items])
    for i, m in enumerate(items, 1):
        v = m.values.dropna()
        fig.add_trace(go.Scatter(x=v.values, y=[0] * len(v), mode="markers", name="제주 다른 읍면동",
                                 marker=dict(color=C["context"], size=10, line=dict(color="#FFFFFF", width=2)),
                                 showlegend=i == 1, hovertext=[f"{a}<br>{fmt(x, m.unit, m.digits)}" for a, x in v.items()],
                                 hoverinfo="text"), row=i, col=1)
        marks = ([(target, C["sea"], "대상 지역", "diamond", "top center")] if target else []) + \
                [(c, C["tangerine"], "비교 지역", "circle", "bottom center") for c in compare]
        for a, color, nm, sym, pos in marks:
            if a in v.index:
                fig.add_trace(go.Scatter(x=[v[a]], y=[0], mode="markers+text", text=[f"<b>{a}</b>"], textposition=pos,
                                         textfont=dict(color=C["basalt"], size=12), name=nm,
                                         hovertext=[f"{a}<br>{fmt(float(v[a]), m.unit, m.digits)}"], hoverinfo="text",
                                         showlegend=(i == 1 and (a == target or (compare and a == compare[0]))),
                                         marker=dict(color=color, size=16, symbol=sym, line=dict(color="#FFFFFF", width=2))),
                              row=i, col=1)
        fig.update_yaxes(visible=False, range=[-1.8, 1.8], row=i, col=1)
    fig.update_annotations(font=dict(size=13, color=C["basalt"]), xanchor="left", x=0)
    return plotly_layout(fig, f"제주 읍면동 중 {target}의 위치" if target else "제주 읍면동 분포", 150 * len(items) + 110)


def rank_chart(m, highlight: list[str], top: int = 15, show_all: bool = False) -> go.Figure | None:
    """가로 막대 순위. show_all=True면 자료에 들어 있는 읍면동 전부(목록형 자료)."""
    v = m.values.dropna().sort_values(ascending=False)
    if len(v) < 2 and not (show_all and len(v)):
        return None
    show = list(v.index if show_all else v.index[:top])
    for h in highlight:
        if h in v.index and h not in show:
            show.append(h)
    v = v[show][::-1]
    target = highlight[0] if highlight else None
    colors = [C["sea"] if a == target else C["tangerine"] if a in highlight else C["context"] for a in v.index]
    fig = go.Figure(go.Bar(x=v.values, y=list(v.index), orientation="h", marker_color=colors,
                           text=[fmt(x, _u(m), m.digits) for x in v.values], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.update_xaxes(showgrid=True, range=[0, float(v.max()) * 1.28])
    if show_all:
        title = f"{m.name} — 자료에 들어 있는 읍면동 {len(v)}곳 ({m.period})"
        missing = [h for h in highlight if h not in m.values.dropna().index]
        if missing:
            title += f" · {', '.join(missing)} 없음"
    else:
        title = f"{m.name} — 읍면동 상위 {min(top, len(m.values.dropna()))}곳 ({m.period})"
    return plotly_layout(fig, title, 28 * len(v) + 120)


def compare_chart(metrics, places: list[str]) -> go.Figure | None:
    """지역 2~4곳 비교: 지표마다 작은 가로 막대 그래프(값 크기가 달라도 각자 축을 쓴다)."""
    items = [m for m in metrics if not m.reason and m.values.reindex(places).notna().sum() >= 2]
    if not items:
        return None
    row_h = 30 * len(places) + 70
    fig = make_subplots(rows=len(items), cols=1, vertical_spacing=min(0.12, 60 / (row_h * len(items))),
                        subplot_titles=[f"<b>{m.name}</b>  <span style='color:{C['ink3']}'>{m.period}</span>" for m in items])
    for i, m in enumerate(items, 1):
        v = m.values.reindex(places)
        ys = [p for p in places][::-1]
        xs = [v[p] for p in ys]
        fig.add_trace(go.Bar(x=xs, y=ys, orientation="h", showlegend=False, cliponaxis=False,
                             marker_color=[C["sea"] if p == places[0] else C["tangerine"] for p in ys],
                             text=[fmt(x, _u(m), m.digits) if pd.notna(x) else "자료 없음" for x in xs], textposition="outside",
                             hovertemplate="%{y}: %{text}<extra></extra>"), row=i, col=1)
        mx = max([x for x in xs if pd.notna(x)] or [1])
        fig.update_xaxes(range=[0, mx * 1.3], showgrid=True, row=i, col=1)
    fig.update_annotations(font=dict(size=13, color=C["basalt"]), xanchor="left", x=0)
    fig.update_layout(bargap=0.35)
    return plotly_layout(fig, f"지역 비교: {' · '.join(places)}", row_h * len(items) + 90)


def trend_chart(m, place: str) -> go.Figure | None:
    """월별 꺾은선. 빠진 달은 회색 점선으로 잇고 '자료 없음'을 적는다."""
    if m.trend is None or len(m.trend) < 2:
        return None
    s = m.trend
    missing = [x for x in (getattr(m, "missing", None) or []) if s.index[0] < x < s.index[-1] or x > s.index[-1]]
    months = sorted(set(s.index) | set(missing))
    full = s.reindex(months)
    fig = go.Figure()
    if missing:
        fig.add_trace(go.Scatter(x=months, y=full.interpolate(limit_area="inside").values, mode="lines", connectgaps=True,
                                 line=dict(color=C["context"], width=2, dash="dot"), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=months, y=full.values, mode="lines+markers+text", connectgaps=False,
                             line=dict(color=C["sea"], width=2.5), marker=dict(size=8),
                             text=[fmt(x, m.unit, m.digits) if pd.notna(x) else "" for x in full.values],
                             textposition="top center", name=place, showlegend=False))
    gap = full.interpolate(limit_area="inside")
    for x in missing:
        y = gap.get(x)
        if pd.notna(y):
            fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=["자료 없음"], textposition="bottom center",
                                     marker=dict(color="#FFFFFF", size=9, line=dict(color=C["context"], width=2)),
                                     textfont=dict(color=C["ink3"], size=11), hoverinfo="skip", showlegend=False))
    fig.update_xaxes(type="category")
    return plotly_layout(fig, f"{place} {m.name} 월별 추이", 380)


def cross_chart(res) -> go.Figure | None:
    """조건 2개 교차: 가로 A, 세로 B, 점 = 읍면동, 조건에 맞는 곳 강조."""
    c = res.cross
    if not c:
        return None
    df, hits = c["frame"], set(c["hits"])
    byid = {m.id: m for m in res.metrics}
    a, b = byid[c["a"]], byid[c["b"]]
    rest = df[~df.index.isin(hits)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rest["A"], y=rest["B"], mode="markers", name="다른 읍면동",
                             marker=dict(color=C["context"], size=10, line=dict(color="#FFFFFF", width=1.5)),
                             hovertext=[f"{i}<br>{a.name} {fmt(x, a.unit, a.digits)}<br>{b.name} {fmt(y, b.unit, b.digits)}"
                                        for i, x, y in zip(rest.index, rest["A"], rest["B"])], hoverinfo="text"))
    h = df[df.index.isin(hits)]
    fig.add_trace(go.Scatter(x=h["A"], y=h["B"], mode="markers+text", name="조건에 맞는 곳", text=list(h.index),
                             textposition="top center", textfont=dict(color=C["basalt"], size=12),
                             marker=dict(color=C["sea"], size=14, line=dict(color="#FFFFFF", width=2)),
                             hovertext=[f"{i}<br>{a.name} {fmt(x, a.unit, a.digits)}<br>{b.name} {fmt(y, b.unit, b.digits)}"
                                        for i, x, y in zip(h.index, h["A"], h["B"])], hoverinfo="text"))
    cut = c["cut"]
    xa = cut["a_hi"] if c["want"][0] == "high" else cut["a_lo"]
    pos = df["A"][df["A"] > 0]
    logx = len(pos) == len(df) and pos.max() / max(pos.median(), 1e-9) > 5  # 한쪽에 몰리면 로그 눈금으로 펼친다
    x0, x1 = float(df["A"].min()), float(df["A"].max())
    y0, y1 = float(df["B"].min()), float(df["B"].max())
    guide = dict(mode="lines", line=dict(color=C["tangerine"], dash="dash", width=1.5), hoverinfo="skip", showlegend=False)
    fig.add_trace(go.Scatter(x=[xa, xa], y=[y0, y1], **guide))
    fig.add_trace(go.Scatter(x=[x0, x1], y=[cut["b_med"]] * 2, **guide))
    fig.update_xaxes(title_text=f"{a.name} →" + (" (로그 눈금)" if logx else ""), title_font=dict(size=12), showgrid=True,
                     type="log" if logx else "linear")
    fig.update_yaxes(title_text=f"{b.name.split('(')[0].strip()} →", title_font=dict(size=12), showgrid=True)
    return plotly_layout(fig, c["desc"], 460)


def choose_charts(res, slots: dict) -> list[tuple[str, go.Figure, str]]:
    """결과 모양에 맞춰 그래프를 고른다(코드 규칙만, 항상 같은 결과). [(탭 이름, 그림, 고른 이유)]."""
    from graph.pipeline import MIN_COMPARE
    ok = [m for m in res.metrics if not m.reason]
    if not ok:
        return []
    asked = [m for m in ok if getattr(m, "asked", False)] or ok
    m0 = asked[0]
    area = res.places[0] if res.places else None
    out = []
    # 0) 조건 2개 교차
    if getattr(res, "cross", None):
        f = cross_chart(res)
        if f:
            out.append(("조건 교차", f, "조건 두 개를 함께 보려고 가로·세로에 한 지표씩 두고 읍면동을 점으로 찍었습니다(점선이 기준)"))
    # 1) 추이(추이를 물었거나 지역이 하나일 때 맨 앞) / 2) 지역 2~4곳 비교
    tm = next((m for m in asked + ok if m.trend is not None and len(m.trend) >= 2), None)
    trend = None
    if tm is not None and area:
        f = trend_chart(tm, area)
        if f:
            why = f"{area}의 월별 값이 있어 꺾은선으로 보여 줍니다" + (" (빠진 달은 점선)" if getattr(tm, "missing", None) else "")
            trend = ("월별 추이", f, why)
    comp = None
    if 2 <= len(res.places) <= 4:
        f = compare_chart(asked + [m for m in ok if m not in asked], res.places)
        if f:
            comp = ("지역 비교", f, f"지역 {len(res.places)}곳 비교라 지표마다 막대를 나란히 보여 줍니다")
    first_trend = slots.get("analysis") == "trend" or len(res.places) < 2
    out += [x for x in ((trend, comp) if first_trend else (comp, trend)) if x]
    # 3~5) 순위 막대(하나만)
    n = int(m0.values.notna().sum())
    if n and n < MIN_COMPARE:
        f = rank_chart(m0, res.places, show_all=True)
        if f:
            out.append(("들어 있는 읍면동", f, f"이 자료는 읍면동 {n}곳만 담고 있어 들어 있는 곳만 막대로 보여 줍니다"))
    elif n >= 2 and (not area or slots.get("analysis") == "rank"):
        f = rank_chart(m0, res.places or ([res.focus] if res.focus else []), top=10)
        if f:
            out.append(("상위 10곳", f, "어느 읍면동이 높은지 묻는 질문이라 상위 10곳을 막대로 보여 줍니다"))
    elif n >= 2 and area:
        f = rank_chart(m0, res.places, top=15)
        if f:
            out.append(("읍면동 순위", f, "상위 15곳과 대상 지역(15위 밖이면 맨 아래)을 막대로 보여 줍니다"))
    # 보조) 지표 2개 이상 + 지역 → 점 분포도
    if area and len([m for m in ok if m.values.notna().sum() >= 2]) >= 2:
        f = position_chart(ok, area, res.places[1:])
        if f:
            out.append(("한눈에 보는 위치", f, "여러 지표에서 제주 읍면동 사이 위치를 점으로 함께 보여 줍니다"))
    return out
