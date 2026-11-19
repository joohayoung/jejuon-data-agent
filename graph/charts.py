"""그래프(plotly, B 디자인 기준 tools/theme.py)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from graph.pipeline import fmt
from tools.theme import C, plotly_layout


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


def rank_chart(m, highlight: list[str], top: int = 15) -> go.Figure | None:
    v = m.values.dropna().sort_values(ascending=False)
    if len(v) < 2:
        return None
    show = list(v.index[:top])
    for h in highlight:
        if h in v.index and h not in show:
            show.append(h)
    v = v[show][::-1]
    colors = [C["sea"] if a == (highlight[0] if highlight else None) else C["tangerine"] if a in highlight else C["context"] for a in v.index]
    fig = go.Figure(go.Bar(x=v.values, y=list(v.index), orientation="h", marker_color=colors,
                           text=[fmt(x, m.unit, m.digits) for x in v.values], textposition="outside",
                           hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.update_xaxes(showgrid=True)
    return plotly_layout(fig, f"{m.name} — 읍면동 상위 {min(top, len(v))}곳 ({m.period})", 28 * len(v) + 120)


def trend_chart(m, place: str) -> go.Figure | None:
    if m.trend is None or len(m.trend) < 2:
        return None
    s = m.trend
    fig = go.Figure(go.Scatter(x=list(s.index), y=s.values, mode="lines+markers+text", line=dict(color=C["sea"], width=2.5),
                               marker=dict(size=8), text=[fmt(x, m.unit, m.digits) for x in s.values], textposition="top center",
                               name=place))
    return plotly_layout(fig, f"{place} {m.name} 월별 추이", 380)
