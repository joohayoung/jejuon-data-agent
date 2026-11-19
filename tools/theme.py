"""화면·그래프·리포트 공통 디자인 기준.

- 서체: 대한민국 정부 디자인 시스템(KRDS) 기본 서체 Pretendard GOV를 먼저 쓰고, 없으면 같은 계열 Noto Sans KR → 맑은 고딕.
  외부 CDN은 쓰지 않는다(센터 PC는 인터넷이 없을 수 있음).
- 색: 제주 자연에서 따온 색(바다 청록·감귤·현무암 회색). 제주특별자치도 공식 로고·상징색을 쓰지 않는다.
  그래프 두 색(대상 #0081A7, 비교 #DD6418)은 색각 이상·대비 검사(dataviz validate_palette, light) 모두 통과.
- 판정은 색만으로 전하지 않는다: 아이콘 + 글자 + 색을 함께 쓴다.
"""
from __future__ import annotations

import html

FONT = "'Pretendard GOV', 'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"

C = {
    "sea": "#0081A7",        # 그래프: 대상 지역(제주 바다)
    "sea_ui": "#006F8F",     # 버튼·링크·강조 글자(흰 글자 대비 확보용으로 한 단계 진하게)
    "sea_deep": "#0B3B4F",   # 머리 배너 진한 쪽
    "sea_soft": "#E6F4F8",   # 연한 배경
    "tangerine": "#DD6418",  # 그래프: 비교 지역(감귤)
    "tangerine_soft": "#FDF0E7",
    "basalt": "#1F2933",     # 본문 글자(현무암)
    "ink2": "#4A5563",       # 보조 글자
    "ink3": "#6B7685",       # 흐린 글자
    "line": "#E2E7ED",       # 테두리
    "bg": "#F5F7F9",         # 화면 바탕(돌담 회색)
    "card": "#FFFFFF",
    "context": "#C3CBD4",    # 그래프: 나머지 읍면동(배경 점)
    "grid": "#EDF0F3",
}

# 판정 배지: (아이콘, 글자색, 배경색). 상태색은 계열색과 따로 둔다.
JUDGE = {
    "유리": ("▲", "#0E6B3A", "#E3F4EA"),
    "불리": ("▼", "#A8261C", "#FDECEA"),
    "보통": ("●", "#4A5563", "#EEF1F4"),
    "높음": ("▲", "#1D5A99", "#E7F0FB"),
    "낮음": ("▼", "#1D5A99", "#E7F0FB"),
    "증가": ("▲", "#0E6B3A", "#E3F4EA"),
    "감소": ("▼", "#A8261C", "#FDECEA"),
    "정체": ("■", "#4A5563", "#EEF1F4"),
    "확인 불가": ("!", "#7A4D00", "#FFF3D6"),
    "가능": ("✓", "#0E6B3A", "#E3F4EA"),
    "계산 가능": ("✓", "#0E6B3A", "#E3F4EA"),
    "조건부": ("!", "#7A4D00", "#FFF3D6"),
    "불가": ("✕", "#A8261C", "#FDECEA"),
}


def badge(label: str, extra: str = "") -> str:
    icon, fg, bg = JUDGE.get(label, ("●", C["ink2"], "#EEF1F4"))
    return (f'<span class="jj-badge" style="color:{fg};background:{bg}">'
            f'<span aria-hidden="true">{icon}</span> {html.escape(label)}{html.escape(extra)}</span>')


def esc(s) -> str:
    return html.escape(str(s))


CSS = f"""
<style>
:root {{
  --sea:{C['sea']}; --sea-ui:{C['sea_ui']}; --sea-deep:{C['sea_deep']}; --sea-soft:{C['sea_soft']};
  --tang:{C['tangerine']}; --tang-soft:{C['tangerine_soft']};
  --ink:{C['basalt']}; --ink2:{C['ink2']}; --ink3:{C['ink3']}; --line:{C['line']}; --bg:{C['bg']};
}}
html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea {{ font-family: {FONT} !important; }}
.stApp {{ background: var(--bg); color: var(--ink); }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 6rem; max-width: 1280px; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid var(--line); }}
[data-testid="stSidebar"] .block-container {{ padding-top: 1rem; }}
h1, h2, h3, h4 {{ color: var(--ink); letter-spacing: -0.01em; }}
p, li, .stMarkdown {{ font-size: 1rem; line-height: 1.65; }}

/* 머리 배너 */
.jj-hero {{
  background: linear-gradient(120deg, var(--sea-deep) 0%, #0A5E7A 55%, var(--sea) 100%);
  color: #fff; border-radius: 18px; padding: 22px 28px 20px; margin-bottom: 14px;
  box-shadow: 0 6px 20px rgba(11,59,79,.18); position: relative; overflow: hidden;
}}
.jj-hero:after {{ content:""; position:absolute; right:-60px; top:-60px; width:220px; height:220px;
  border-radius:50%; background: radial-gradient(circle, rgba(221,100,24,.55) 0%, rgba(221,100,24,0) 70%); }}
.jj-brand {{ display:flex; align-items:center; gap:11px; margin: 10px 0 12px; position:relative; z-index:1; }}
.jj-brand .logo svg {{ display:block; border-radius:13px; box-shadow: 0 0 0 2px rgba(255,255,255,.55), 0 4px 12px rgba(0,0,0,.18); }}
.jj-brand b {{ font: 800 1.75rem Arial, sans-serif; letter-spacing:-1.5px; color:#fff; }}
.jj-brand b span {{ color:#a9ede1; }}
.jj-brand i {{ height:20px; border-left:1px solid rgba(255,255,255,.45); }}
.jj-brand em {{ font-style:normal; font-weight:700; font-size:1rem; color: rgba(255,255,255,.92); letter-spacing:-.02em; }}
.jj-hero .eyebrow {{ font-size: .85rem; opacity: .85; letter-spacing: .04em; }}
.jj-hero h1 {{ color:#fff; font-size: 1.6rem; font-weight: 800; margin: 2px 0 6px; letter-spacing:-.02em; }}
.jj-hero p {{ color: rgba(255,255,255,.9); margin: 0 0 12px; font-size: 1rem; }}
.jj-chip {{ display:inline-block; padding: 4px 11px; margin: 0 6px 6px 0; border-radius: 999px;
  background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.28); font-size: .82rem; color:#fff; }}
.jj-chip b {{ font-weight: 700; }}

/* 단계 표시 */
.jj-steps {{ display:flex; gap:8px; margin: 4px 0 18px; flex-wrap: wrap; }}
.jj-step {{ flex:1; min-width: 120px; padding: 10px 12px; border-radius: 12px; background:#fff;
  border:1px solid var(--line); color: var(--ink3); font-size:.9rem; }}
.jj-step .n {{ display:inline-block; width:22px; height:22px; line-height:22px; text-align:center; border-radius:50%;
  background:#EEF1F4; color:var(--ink3); font-weight:700; font-size:.8rem; margin-right:6px; }}
.jj-step.done {{ color: var(--ink2); }}
.jj-step.done .n {{ background: var(--sea-soft); color: var(--sea-ui); }}
.jj-step.now {{ border-color: var(--sea-ui); color: var(--ink); font-weight:700; box-shadow: 0 0 0 3px rgba(0,111,143,.12); }}
.jj-step.now .n {{ background: var(--sea-ui); color:#fff; }}

/* 카드 */
.jj-card {{ background:#fff; border:1px solid var(--line); border-radius:16px; padding:18px 20px; height:100%;
  box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
.jj-card h4 {{ margin:0 0 4px; font-size:1rem; color: var(--ink2); font-weight:700; }}
.jj-ind {{ display:flex; flex-direction:column; gap:6px; min-height: 178px; }}
.jj-ind .top {{ display:flex; justify-content:space-between; align-items:center; gap:8px; }}
.jj-ind .name {{ font-weight:700; color: var(--ink); font-size:1.02rem; }}
.jj-ind .val {{ font-size:1.65rem; font-weight:800; color: var(--ink); letter-spacing:-.02em; line-height:1.2;
  font-variant-numeric: tabular-nums; }}
.jj-ind .val .unit {{ font-size:.95rem; font-weight:600; color: var(--ink2); margin-left:3px; letter-spacing:0; }}
.jj-plan {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; padding:10px 2px;
  border-bottom:1px solid var(--line); }}
.jj-plan:last-child {{ border-bottom:none; }}
.jj-plan .name {{ font-weight:700; color: var(--ink); min-width: 110px; }}
.jj-plan .src {{ color: var(--ink2); font-size:.88rem; flex:1; }}
.jj-ind .val.na {{ font-size:1.1rem; color: var(--ink3); font-weight:700; }}
.jj-ind .meta {{ color: var(--ink2); font-size:.9rem; }}
.jj-ind .src {{ color: var(--ink3); font-size:.8rem; border-top:1px dashed var(--line); padding-top:8px; margin-top:auto; }}
.jj-ind .note {{ color:#7A4D00; font-size:.82rem; }}
.jj-badge {{ display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:999px;
  font-size:.82rem; font-weight:700; white-space:nowrap; }}

/* 숫자 타일 */
.jj-kpi {{ background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px; }}
.jj-kpi .k {{ color: var(--ink2); font-size:.86rem; }}
.jj-kpi .v {{ font-size:1.9rem; font-weight:800; color: var(--ink); font-variant-numeric: tabular-nums; }}
.jj-kpi .v small {{ font-size:.95rem; color: var(--ink3); font-weight:600; margin-left:2px; }}

/* 안내 띠 */
.jj-note {{ background: var(--sea-soft); border-left: 4px solid var(--sea-ui); padding: 10px 14px; border-radius: 8px;
  color: var(--ink); font-size:.92rem; }}
.jj-warn {{ background:#FFF3D6; border-left:4px solid #C98500; padding:10px 14px; border-radius:8px; color:#5C3B00; font-size:.92rem; }}
.jj-answer {{ background: var(--sea-soft); border:1px solid rgba(0,111,143,.25); border-left:6px solid var(--sea-ui);
  padding:18px 22px; border-radius:14px; margin-bottom:14px; }}
.jj-answer .a {{ font-size:1.22rem; font-weight:800; color: var(--ink); line-height:1.55; letter-spacing:-.01em; }}
.jj-answer .n {{ color: var(--ink2); font-size:.88rem; margin-top:8px; line-height:1.5; }}
.jj-answer .w {{ color:#5C3B00; background:#FFF3D6; border-radius:8px; padding:6px 10px; font-size:.9rem; margin-top:10px; font-weight:600; }}
.jj-interp {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin: -2px 0 8px; }}
.jj-interp .t {{ font-size:.85rem; color: var(--ink3); font-weight:700; margin-right:4px; }}
.jj-chip2 {{ background:#fff; border:1px solid var(--line); border-radius:999px; padding:3px 10px; font-size:.84rem; color: var(--ink2); }}
.jj-chip2 b {{ color: var(--ink3); font-weight:700; margin-right:3px; }}
.jj-answer .r {{ font-size:1.02rem; color: var(--ink); line-height:1.6; margin-top:6px; }}
.jj-answer .by {{ font-size:.78rem; color: var(--sea-ui); font-weight:700; margin-top:6px; }}
.jj-why {{ color: var(--ink3); font-size:.85rem; margin: -4px 0 6px; }}
.jj-section {{ font-size:1.25rem; font-weight:800; color: var(--ink); margin: 26px 0 10px; display:flex; align-items:center; gap:8px; }}
.jj-section:before {{ content:""; width:6px; height:20px; border-radius:3px; background: var(--tang); display:inline-block; }}
.jj-caption {{ color: var(--ink3); font-size:.85rem; }}

/* Streamlit 기본 요소 다듬기 */
.stButton > button, .stDownloadButton > button {{ border-radius: 10px; min-height: 44px; font-weight: 700; }}
.stButton > button[kind="primary"] {{ background: var(--sea-ui); border-color: var(--sea-ui); }}
.stButton > button[kind="primary"]:hover {{ background: #005A75; border-color:#005A75; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 16px; }}
[data-testid="stChatMessage"] {{ background: #fff; border:1px solid var(--line); border-radius:14px; }}
[data-testid="stDataFrame"] {{ border-radius: 12px; overflow:hidden; }}
.stTabs [data-baseweb="tab"] {{ font-weight:700; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
</style>
"""


def plotly_layout(fig, title: str = "", height: int = 420):
    """그래프 공통: 가는 선, 흐린 격자, 본문색 글자. (dataviz: 한 축, 범례는 2계열 이상일 때만)"""
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color=C["basalt"]), x=0, xanchor="left"),
        font=dict(family=FONT.replace("'", ""), size=13, color=C["ink2"]),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", height=height,
        margin=dict(l=20, r=20, t=60 if title else 20, b=40),
        hoverlabel=dict(bgcolor="#FFFFFF", font=dict(color=C["basalt"])),
        legend=dict(orientation="h", y=-0.12, x=0, xanchor="left", yanchor="top", font=dict(color=C["basalt"])),
    )
    fig.update_xaxes(showgrid=True, gridcolor=C["grid"], zeroline=False, linecolor=C["line"])
    fig.update_yaxes(showgrid=True, gridcolor=C["grid"], zeroline=False, linecolor=C["line"])
    return fig
