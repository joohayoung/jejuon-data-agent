"""질문 1건 처리: 해석 결과(슬롯) → 렌즈(분석 관점) → 지표별 자료 선택·검증·계산 → 판정·문장.

LLM은 해석 단계에서만 쓴다. 자료 선택·계산·판정·문장의 숫자는 모두 코드가 만든다.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from graph import access as da
from graph import engine as en
from tools.rank_areas import quartile_label, rank

ROOT = Path(__file__).resolve().parents[1]
QUANTILE = 0.25
MIN_COMPARE = 22  # 43개 읍면동의 절반 이상에 값이 있어야 높음·보통·낮음 판정. 일부 지점만 담은 목록형 자료는 '참고'
TREND_BAND = 0.03   # 추이 판단: 첫·끝 달 차이 ±3% 이내는 '큰 변화 없음'(노형동 달 간 변화 −1.8~+4.1% 근거, 평가 세트로 조정)
STALE_MONTHS = 24   # 지표 기준 시점이 오늘보다 24개월 이상 오래되면 '멈춘 자료' 경고
LENS_SIMPLE = 2     # 개수·단순 조회 질문에 붙이는 관점 지표 최대 수
BANNED = ["차려도 된다", "차려도 됩니다", "하지 마", "추천합니다", "추천한다", "안 된다", "안 됩니다"]


@lru_cache(maxsize=1)
def concept_notes() -> dict:
    return yaml.safe_load((Path(__file__).parent / "concept_notes.yaml").read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def lenses() -> dict:
    return yaml.safe_load((Path(__file__).parent / "lenses.yaml").read_text(encoding="utf-8"))["lenses"]


@dataclass
class Result:
    question: str
    slots: dict
    status: str = "answered"             # answered | partial | held | ask
    ask: str | None = None
    lens: str | None = None
    lens_title: str | None = None
    focus: str | None = None                          # 지역 없는 질문에서 카드 기준 지역(1위)
    places: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    lead: str = ""
    notes_top: list = field(default_factory=list)     # 결론 아래 해설(일상 말 ↔ 자료 뜻)
    warnings: list = field(default_factory=list)      # 오래된 자료 등 답 카드 경고
    cross: dict | None = None                         # 조건 2개 교차(모델 goal 기준)
    sentences: list = field(default_factory=list)
    limits: list = field(default_factory=list)
    used: list = field(default_factory=list)          # 허브 ID
    rejected: dict = field(default_factory=dict)      # 허브 ID → 사유
    log: list = field(default_factory=list)
    started: float = field(default_factory=time.time)

    def step(self, stage: str, by: str, detail: str, t0: float, stats: dict | None = None):
        rec = {"stage": stage, "by": by, "detail": detail, "sec": round(time.time() - t0, 2)}
        for c in (stats or {}).get("calls", [])[-1:]:
            rec.update(prompt_eval_count=c.get("prompt_eval_count"), eval_count=c.get("eval_count"))
        self.log.append(rec)


# ---------------- 표시 ----------------

def won(v: float) -> str:
    """큰 금액을 읽기 쉽게: 186,282,420 → '1억 8,628만', 41,695,300 → '4,170만'."""
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e8:
        eok, man = divmod(round(a / 1e4), 10000)
        return f"{sign}{eok:,}억" + (f" {man:,}만" if man else "")
    if a >= 1e4:
        return f"{sign}{round(a / 1e4):,}만"
    return f"{sign}{a:,.0f}"


def fmt(v, unit: str = "", digits: int = 0) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    if unit == "원" and abs(v) >= 1e4:
        return f"{won(float(v))} 원"
    if digits == 0 and abs(v) < 100 and v != int(v):
        digits = 2
    s = f"{v:,.{digits}f}"
    if unit in ("%", "개", "곳", "건"):
        return f"{s}{unit}"
    return f"{s} {unit}" if unit else s


def unit_label(m: en.Measure) -> str:
    if m.op == "count":
        return "개"
    if m.unit == "지표":
        return "(지표)"
    return m.unit or ""


# ---------------- 지표 하나 만들기 ----------------

def _measure(spec: dict, filters: dict, period, anchor, places, res: Result):
    concept = spec["concept"]
    f = {spec["filter"]: filters[spec["filter"]]} if spec.get("filter") and filters.get(spec["filter"]) else {}
    m, cands, rej = en.choose_measure(concept, f, "읍면동")
    if not m and f and spec.get("soft"):
        # 업종 등 구분값으로 나눌 수 없는 개념(예: 방문지표)은 구분값 없이 계산한다.
        # 다만 같은 구분(업종) 컬럼이 있는데 값만 못 찾았으면 '전체 합계'라고 알린다.
        m, cands, rej2 = en.choose_measure(concept, {}, "읍면동")
        if m:
            dim, val = next(iter(f.items()))
            cols = [c for _, c in en.kg().keys(str(m.dataset))[2]]
            if any(c.get("role") == "구분값" and c.get("concept") == dim for c in cols):
                m.notes.append(f"허브 {m.dataset} 자료에서 '{val}'({dim}) 값을 찾지 못해 전체 {dim} 합계로 계산했습니다.")
            spec["applied"] = False
        rej = {**rej, **rej2}
    elif m and f:
        spec["applied"] = True
    for h, why in rej.items():
        res.rejected.setdefault(h, f"{concept}: {why}")
    if not m:
        why = sorted({w for w in rej.values()})
        g = en.kg()
        names = [f"허브 {h} {g.n.get(f'ds:{h}', {}).get('title', '')[:24]}({w})" for h, w in list(rej.items())[:3]]
        detail = (" 지식 그래프의 후보: " + "; ".join(names)) if names else " 지식 그래프에 이 개념을 재는 자료가 없습니다."
        return None, f"'{concept}'을(를) 읍면동 단위로 계산할 수 있는 자료가 없습니다.{detail}"
    return m, None


def build_metric(mid: str, name: str, num: dict, den: dict | None, scale: float, unit: str | None, digits: int,
                 filters: dict, asked_period, anchor, places, res: Result, offline: bool) -> en.Metric:
    t0 = time.time()
    mn, why = _measure(num, filters, asked_period, anchor, places, res)
    if not mn:
        res.step(f"{mid} 자료 선택", "코드(그래프)", f"{name}: {why}", t0)
        return en.Metric(mid, name, unit or "", pd.Series(dtype=float), reason=why)
    md = None
    if den:
        md, why = _measure(den, filters, asked_period, anchor, places, res)
        if not md:
            return en.Metric(mid, name, unit or "", pd.Series(dtype=float), reason=why, measures=[mn])
    anchor2 = anchor or (mn.data_end if mn.snapshot else None) or (md.data_end if md and md.snapshot else None)
    pn = en.default_period(mn, asked_period, anchor2)
    pd_ = en.default_period(md, asked_period, anchor2) if md else None
    sel = f"{name}: 허브 {mn.dataset}({mn.title[:24]}) {mn.op}({mn.column or '행 수'})"
    if mn.filters:
        sel += f" 필터 {mn.filters}"
    if md:
        sel += f" ÷ 허브 {md.dataset}({md.title[:24]}) {md.op}({md.column or '행 수'})"
    dev = list(dict.fromkeys(mn.dev_notes + (md.dev_notes if md else [])))
    if dev:
        sel += " · 컬럼 메모: " + " / ".join(dev)
    res.step(f"{mid} 자료 선택·템플릿 계획", "코드(그래프)", sel, t0)

    t0 = time.time()
    errs = en.validate(mn, pn) + (en.validate(md, pd_) if md else [])
    j = None
    if md:
        j = en.joinable(mn.dataset, md.dataset)
        if not j:
            errs.append(f"허브 {mn.dataset}와 {md.dataset}는 지식 그래프에서 결합할 수 없는 조합입니다(지역 단위·기간 불일치).")
    res.step(f"{mid} 검증", "코드", "통과" if not errs else " / ".join(errs), t0)
    if errs:
        return en.Metric(mid, name, unit or "", pd.Series(dtype=float), reason=" ".join(errs), measures=[x for x in (mn, md) if x])

    t0 = time.time()
    try:
        sn, tn, inf_n = en.compute(mn, pn, places, offline=offline)
        if md:
            sd, td, inf_d = en.compute(md, pd_, places, offline=offline)
    except da.DataAccessError as e:
        res.step(f"{mid} 조회·계산", "코드", f"보류: {e}", t0)
        srcs = " / ".join(f"허브 {x.dataset} {x.title}" for x in (mn, md) if x)
        why = f"필요한 자료({srcs})는 찾았지만 받아오지 못했습니다 — {e}"
        return en.Metric(mid, name, unit or "", pd.Series(dtype=float), reason=why, measures=[x for x in (mn, md) if x])
    notes = list(mn.notes) + (list(md.notes) if md else [])
    for x, p in ((mn, pn), (md, pd_)):
        # 다른 지표의 시점(anchor)이 이 자료 기간 밖이라 이 자료의 최신 달로 계산한 경우
        if x and p and anchor2 and not x.snapshot and not asked_period and p[1][:7] != anchor2[:7]:
            notes.append(f"허브 {x.dataset} 자료는 {(x.data_end or p[1])[:7]}까지라 다른 지표({anchor2[:7]})와 같은 시점으로 "
                         f"맞추지 못하고 {p[1][:7]}{ro(p[1][:7])} 계산했습니다.")
    for x, inf in ((mn, inf_n), (md, inf_d if md else None)):
        if x and inf and inf.get("unmatched"):
            notes.append(f"허브 {x.dataset}: 지역을 읍면동으로 정할 수 없는 {inf['unmatched']}행(여러 행정동에 걸친 법정동·불완전한 주소 등)은 빼고 계산했습니다.")
        if x and not x.snapshot and not x.time_column and x.op in ("sum", "count"):
            notes.append(f"허브 {x.dataset}: 자료에 날짜 구분이 없어 받은 자료 전체를 합산했습니다(기간 표시는 자료의 최신 기준일).")
    if md:
        vals = (sn / sd.where(sd > 0)) * scale
        complete = inf_n["complete"] and inf_d["complete"]
        total = (tn / td * scale) if (tn and td and complete) else None
        kind = "ratio"
        u = unit or ""
        per = en.period_label(mn, pn) if mn.snapshot else en.period_label(md, pd_)
        if mn.snapshot and not md.snapshot:
            per = f"{en.period_label(mn, pn)} ÷ {en.period_label(md, pd_)}"
    else:
        vals, total, complete, kind = sn, tn, inf_n["complete"], mn.op
        if not complete or mn.unit == "지표":
            # '지표'(가공 지수)는 읍면동끼리 더한 '제주 전체' 값이 사람 수처럼 읽혀 오해를 낳으므로 보여 주지 않는다
            total = None
        u = unit or unit_label(mn)
        per = en.period_label(mn, pn)
    for x, per_ in ((mn, pn), (md, pd_)):
        if x and asked_period and not x.snapshot and x.data_end and asked_period[1] > x.data_end:
            notes.append(f"요청 기간({asked_period[0]}~{asked_period[1]}) 중 허브 {x.dataset} 자료는 {x.data_end}까지만 있어 그때까지로 계산했습니다.")
    if mn.unit == "지표" or (md and md.unit == "지표"):
        notes.append("방문·거주지표는 허브가 가공해 제공하는 지표라 사람 수(명)가 아닙니다. 여러 날은 더하지 않고 일평균으로 계산했습니다.")
    if not complete:
        notes.append("제주 전체 읍면동 자료를 받지 못해 질문한 지역만 계산했습니다(순위 판정 보류).")
    srcs = [dict(hub_id=x.dataset, title=x.title, via=x.via, period=en.period_label(x, p),
                 fetched=(inf_n if x is mn else inf_d).get("fetched")) for x, p in ((mn, pn), (md, pd_)) if x]
    res.step(f"{mid} 조회·계산", "코드", f"{per} · 값 있는 읍면동 {int(vals.notna().sum())}곳"
             + ("" if complete else " (요청 지역만)"), t0)
    ends = [p[1] for x, p in ((mn, pn), (md, pd_)) if x and p]
    met = en.Metric(mid, name, u, vals, period=per, sources=srcs, notes=list(dict.fromkeys(notes)),
                    scalar=total, kind=kind, complete=complete, measures=[x for x in (mn, md) if x],
                    joinable=j, digits=digits)
    met.end = min(ends) if ends else None
    return met


# ---------------- 판정 ----------------

def judge(m: en.Metric, area: str | None) -> dict:
    row = {"id": m.id, "지표": m.name, "단위": m.unit, "기준 시점": m.period, "대상": area, "대상 값": None,
           "제주 중앙값": None, "순위": None, "비교 수": None, "판정": "확인 불가", "사유": m.reason, "제주 전체": m.scalar}
    if m.reason:
        return row
    v = m.values.dropna()
    row["비교 수"] = len(v)
    row["제주 중앙값"] = float(v.median()) if len(v) else None
    if not area:
        row["판정"] = "제주 전체"
        return row
    if area not in v.index:
        top = ", ".join(f"{a}({fmt(float(x), m.unit, m.digits)})" for a, x in v.sort_values(ascending=False).head(5).items())
        row["사유"] = (f"이 자료에는 {area} 값이 없습니다. 자료에 들어 있는 읍면동은 {len(v)}곳뿐입니다"
                      + (f": {top}" if top else "") + ".")
        return row
    row["대상 값"] = float(v[area])
    if not m.complete or len(v) < MIN_COMPARE:
        row["판정"] = "참고"
        row["사유"] = ("제주 전체 비교 자료 부족" if not m.complete
                      else f"이 자료는 읍면동 {len(v)}곳만 담고 있어(전체 43곳) 순위 판정을 하지 않습니다")
        return row
    r = rank(v, "none").loc[area]
    row.update({"순위": int(r["rank"]), "판정": quartile_label(int(r["rank"]), int(r["n"]), QUANTILE, "none")})
    return row


# ---------------- 문장(코드) ----------------

def josa(word: str, pair: str = "은는") -> str:
    word = re.sub(r"\s*\([^)]*\)\s*$", "", word or "")
    ch = word[-1] if word else ""
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    if ch.isdigit():  # 영·일·삼·육·칠·팔은 받침 있음
        return pair[0] if ch in "013678" else pair[1]
    return pair[0]


def ro(text: str) -> str:
    """'로/으로' (받침 있으면 '으로', ㄹ받침은 '로')."""
    w = re.sub(r"\s*\([^)]*\)\s*$", "", text or "")
    w = re.sub(r"[^가-힣0-9]+$", "", w)
    ch = w[-1] if w else ""
    if "가" <= ch <= "힣":
        b = (ord(ch) - 0xAC00) % 28
        return "로" if b in (0, 8) else "으로"
    if ch.isdigit():
        return "으로" if ch in "0136" else "로"
    return "로"


VERDICT = {"높음": "높은 편", "낮음": "낮은 편", "보통": "중간 수준"}


def sentence(row: dict, m: en.Metric) -> str | None:
    src = ", ".join(f"허브 {s['hub_id']} {s['title']} {s['period']}" for s in m.sources)
    if row["판정"] == "확인 불가":
        if not m.reason and row.get("대상"):
            return f"{row['대상']}의 {m.name}: {row['사유']} ({src})"
        return f"{m.name}: 계산하지 않았습니다 — {row['사유']}"
    if row["판정"] == "제주 전체":
        if m.scalar is None:
            return None
        return f"제주 전체 {m.name}{josa(m.name)} {fmt(m.scalar, m.unit, m.digits)}입니다. ({src})"
    val = fmt(row["대상 값"], m.unit, m.digits)
    if row["판정"] == "참고":
        extra = f" — {row['사유']}" if row.get("사유") else ""
        return f"{row['대상']}의 {m.name}{josa(m.name)} {val}입니다{extra}. ({src})"
    return (f"{row['대상']}의 {m.name}{josa(m.name)} {val}{ro(val)}, 제주 읍면동 {row['비교 수']}곳 중 {row['순위']}번째로 "
            f"{VERDICT.get(row['판정'], row['판정'])}입니다(중앙값 {fmt(row['제주 중앙값'], m.unit, m.digits)}). ({src})")


# ---------------- 렌즈 ----------------

def pick_lens(slots: dict, question: str) -> str | None:
    """분석 관점은 질문 원문이 아니라 해석 결과(모델이 뽑은 개념·업종)로만 고른다."""
    concepts = set(slots.get("concepts", []))
    if slots.get("filters", {}).get("업종") or "점포수" in concepts:
        return "상권" if "상권" in lenses() else None
    for key, L in lenses().items():
        if concepts & set(L.get("when", {}).get("concepts", [])):
            return key
    return None


LABEL = {"방문인구": "방문", "외국인방문인구": "외국인 방문", "거주인구": "거주", "근무인구": "근무", "점포수": "점포 수",
         "카드이용금액": "카드 이용금액", "충전기수": "충전기 수", "주차면수": "주차면 수", "의료기관수": "의료기관 수",
         "숙박시설수": "숙박시설 수", "교통사고건수": "교통사고 건수", "정류소수": "정류소 수", "주민등록인구": "주민등록 인구"}


def label(concept: str) -> str:
    """화면용 개념 이름(내부 이름 '외국인방문인구' → '외국인 방문')."""
    return LABEL.get(concept, concept)


NICE = {"방문인구": "일평균 방문지표", "외국인방문인구": "일평균 외국인 방문지표", "거주인구": "일평균 거주지표",
        "근무인구": "일평균 근무지표", "점포수": "점포 수"}


def _sig(num, den):
    return (num.get("concept"), None if num.get("soft") else num.get("filter"), (den or {}).get("concept"))


def plan_metrics(slots: dict, question: str) -> tuple[list[dict], str | None]:
    """질문이 직접 묻는 지표 + 렌즈 지표(중복 제외)."""
    out, seen = [], set()
    filters = slots.get("filters", {})
    fval = filters.get("업종")
    fdim = next(iter(filters), None)

    def label(c):
        return f"{fval} {c}" if fval and c == "점포수" else NICE.get(c, c)

    if slots.get("ratio"):
        r = slots["ratio"]
        num = {"concept": r["numerator"], "filter": fdim if r["numerator"] == "점포수" else None}
        den = {"concept": r["denominator"]}
        out.append(dict(name=f"{label(r['numerator'])} ÷ {NICE.get(r['denominator'], r['denominator'])}", num=num, den=den,
                        scale=r.get("scale") or 1, unit=None, digits=2, asked=True))
        seen.add(_sig(num, den))
    for c in slots.get("concepts", [])[:3]:
        num = {"concept": c, "filter": fdim, "soft": c != "점포수"} if fdim else {"concept": c, "filter": None}
        if _sig(num, None) in seen:
            continue
        out.append(dict(name=label(c), num=num, den=None, scale=1, unit=None, digits=0, asked=True))
        if num.get("soft"):
            out[-1]["name_if_filtered"] = f"{fval or filters.get(fdim)} {NICE.get(c, c)}"
        seen.add(_sig(num, None))
    lens = pick_lens(slots, question)
    n_lens, cap = 0, (LENS_SIMPLE if slots.get("analysis") in ("count", "lookup") and not slots.get("ratio") else 6)
    if lens:
        for ind in lenses()[lens]["indicators"]:
            if n_lens >= cap:
                break
            if ind.get("need_filter") and not fval:
                continue
            num, den = dict(ind["num"]), ind.get("den")
            if num.get("filter") and not filters.get(num["filter"]):
                num["filter"] = None
            sig = _sig(num, den)
            if sig in seen:
                for o in out:  # 질문 지표와 같으면 렌즈의 이름·단위를 쓴다
                    if _sig(o["num"], o["den"]) == sig:
                        o.update(name=ind["name"].replace("{업종}", fval or ""), unit=ind.get("unit"),
                                 digits=ind.get("digits", o["digits"]), scale=ind.get("scale", o["scale"]))
                continue
            seen.add(sig)
            n_lens += 1
            out.append(dict(name=ind["name"].replace("{업종}", fval or "").strip(), num=num, den=den,
                            scale=ind.get("scale", 1), unit=ind.get("unit"), digits=ind.get("digits", 0), asked=False))
    return out[:6], lens


# ---------------- 실행 ----------------

def run(question: str, slots: dict, offline: bool | None = None) -> Result:
    if offline is None:  # GRAPH_OFFLINE=1이면 허브 API를 부르지 않고 저장된 자료만 쓴다(시연·시험용)
        import os
        offline = os.environ.get("GRAPH_OFFLINE", "") == "1"
    res = Result(question=question, slots=slots)
    res.places = slots.get("places") or []
    area = res.places[0] if res.places else None
    if slots.get("unsupported"):
        res.status = "held"
        res.lead = f"이 질문은 데이터로 답할 수 없는 부분이 있습니다: {slots['unsupported']}"
        res.limits.append("관측 자료로 미래를 예측하거나, 자료에 없는 값(순이익 등)을 만들지 않습니다.")
        if not slots.get("concepts"):
            return res
    t0 = time.time()
    specs, lens = plan_metrics(slots, question)
    res.lens = lens
    res.lens_title = lenses()[lens]["title"] if lens else None
    res.step("렌즈·지표 구성", "코드", (f"{res.lens_title}: " if lens else "질문 지표만: ") + ", ".join(s["name"] for s in specs), t0)
    if not specs:
        res.status = "held"
        res.lead = "질문에서 계산할 대상을 찾지 못했습니다. '무엇을'(예: 점포 수, 방문객) 알고 싶은지 함께 적어 주세요."
        return res

    # 스냅샷 자료가 있으면 그 날짜의 달로 시점을 맞춘다(같은 시점 비교)
    anchor = None
    asked = tuple(slots["period"]) if slots.get("period") else None
    if not asked:
        for s in specs:
            m, _, _ = en.choose_measure(s["num"]["concept"], {}, "읍면동")
            if m and m.snapshot:
                anchor = m.data_end
                break
    for i, s in enumerate(specs, 1):
        m = build_metric(f"M{i}", s["name"], s["num"], s["den"], s["scale"], s["unit"], s["digits"],
                         slots.get("filters", {}), asked, anchor, res.places, res, offline)
        if s["num"].get("applied") and s.get("name_if_filtered"):
            m.name = s["name_if_filtered"]
        m.asked = s.get("asked", False)
        m.concepts = [s["num"]["concept"]] + ([s["den"]["concept"]] if s.get("den") else [])
        res.metrics.append(m)
    # 질문 지표 중 일부만 계산됐으면, 자료가 없는 지표는 카드에서 빼고 한계에 적는다
    if any(not m.reason for m in res.metrics if getattr(m, "asked", False)):
        for m in [m for m in res.metrics if getattr(m, "asked", False) and m.reason and "계산할 수 있는 자료가 없습니다" in m.reason]:
            res.limits.append(f"'{m.name}'은(는) 계산하지 못했습니다 — {m.reason}")
            res.step(f"{m.id} 제외", "코드", f"{m.name}: 자료 없음", time.time())
            res.metrics.remove(m)
    # 질문이 직접 묻는 지표를 하나도 계산하지 못했으면 '답할 수 없다'고 말하고, 관련 지표(렌즈)로 답을 대신하지 않는다
    asked_ms = [m for m in res.metrics if getattr(m, "asked", False)]
    if asked_ms and all(m.reason for m in asked_ms):
        res.status = "held"
        reasons = list(dict.fromkeys(m.reason for m in asked_ms))
        res.lead = "질문하신 내용은 지금 연결된 자료로 답할 수 없습니다. " + reasons[0]
        res.metrics = asked_ms
        res.rows = [judge(m, area) for m in res.metrics]
        res.sentences = [f"계산하지 못한 이유: {r}" for r in reasons]
        res.limits.append("관련 없어 보이는 다른 지표로 답을 대신하지 않습니다. 데이터 지도의 회색 원(검토했지만 쓰지 못한 자료)과 사유를 확인해 주세요.")
        res.step("답변 보류", "코드", "질문 지표를 모두 계산하지 못함 → 렌즈 지표를 답으로 쓰지 않음", time.time())
        return res
    keep = []
    for i, m in enumerate(res.metrics):
        if m.reason and "계산할 수 있는 자료가 없습니다" in m.reason and not getattr(m, "asked", False):
            res.step(f"{m.id} 제외", "코드", f"{m.name}: {m.reason}", time.time())
            continue
        keep.append(m)
    res.metrics = keep
    if area and (slots.get("analysis") == "trend" or lens == "인구·방문"):
        t0 = time.time()
        for m in res.metrics:
            if m.reason or len(m.measures) != 1 or m.measures[0].snapshot:
                continue
            span = 6
            if asked:
                a0, a1 = dt.date.fromisoformat(asked[0]), dt.date.fromisoformat(asked[1])
                span = max(2, min(24, (a1.year - a0.year) * 12 + a1.month - a0.month + 1))
            tr = en.monthly_trend(m.measures[0], area, months=span, end=(asked[1] if asked else None), offline=offline)
            if len(tr) >= 2:
                m.trend = tr
                tend = asked[1] if asked else (m.measures[0].data_end or tr.index[-1] + "-01")
                if m.measures[0].data_end and tend > m.measures[0].data_end:
                    tend = m.measures[0].data_end
                exp = [x for x in en.expected_months(tend, span) if tr.index[0] <= x <= tr.index[-1] or x > tr.index[-1]]
                m.missing = [x for x in exp if x not in tr.index]
                res.step("월별 추이", "코드", f"{m.name} {area} {tr.index[0]}~{tr.index[-1]} {len(tr)}개월", t0)
                break
        else:
            res.step("월별 추이", "코드", "추이를 그릴 수 있는 달이 2개 미만(받아 둔 자료 부족)", t0)
    for m in res.metrics:
        for x in m.measures:
            if not m.reason and x.dataset not in res.used:
                res.used.append(x.dataset)
    for h in res.used:
        res.rejected.pop(h, None)

    if not area:
        # 지역 없이 '어디가 높은가'를 물으면 1위 지역을 기준으로 카드를 보여 준다(값·순위·판정이 보이도록)
        m0 = next((m for m in res.metrics if not m.reason and m.values.notna().sum() >= 3), None)
        if m0 is not None:
            res.focus = m0.values.dropna().idxmax()
    res.rows = [judge(m, area or res.focus) for m in res.metrics]
    ok = [m for m in res.metrics if not m.reason]
    if not ok:
        res.status = "held"
        res.lead = "필요한 자료를 찾았지만 계산할 수 없었습니다. 아래 사유와 데이터 지도를 확인해 주세요."
    elif len(ok) < len(res.metrics):
        res.status = "partial"
    res.sentences = [x for x in (sentence(r, m) for r, m in zip(res.rows, res.metrics)) if x]
    if not area:  # 지역이 없으면 '어느 동네가 높은지'로 답한다(상위 3곳)
        for m in res.metrics:
            v = m.values.dropna().sort_values(ascending=False)
            if m.reason or len(v) < 3:
                continue
            top = ", ".join(f"{a} {fmt(float(x), m.unit, m.digits)}" for a, x in v.head(3).items())
            res.sentences.insert(0, f"{m.name}{josa(m.name, '이가')} 높은 읍면동: {top} (제주 {len(v)}곳 중, {m.period}).")
            if not res.lead:
                res.lead = f"{m.name}{josa(m.name, '이가')} 가장 높은 곳은 {v.index[0]}({fmt(float(v.iloc[0]), m.unit, m.digits)})이고, 이어서 {v.index[1]}, {v.index[2]} 순입니다. ({m.period})"
            break
    if ok and (not area or slots.get("analysis") == "rank") and len(slots.get("goal") or []) >= 2:
        t0 = time.time()
        res.cross = cross_table(res, slots["goal"])
        res.step("조건 교차", "코드", res.cross["desc"] if res.cross else "조건 2개에 맞는 지표를 찾지 못해 교차하지 않음", t0)
    if ok:
        lf = lead_for(res, slots, area)
        if lf:
            res.lead = (res.lead + " " if slots.get("unsupported") else "") + lf
    if ok:
        if len(res.places) > 1:
            # 지표마다 어느 지역이 더 높은지(기준에 따라 답이 달라질 수 있음을 보여 준다)
            wins = []
            for m in res.metrics:
                v = m.values.reindex(res.places).dropna()
                if m.reason or len(v) < 2:
                    continue
                top = v.idxmax()
                wins.append((m.name, top, " vs ".join(f"{a} {fmt(float(x), m.unit, m.digits)}" for a, x in v.items())))
            if wins:
                res.sentences.insert(0, "지역 비교: " + " / ".join(f"{n}은(는) {a}이(가) 더 높음({d})" for n, a, d in wins) + ".")
    for m in res.metrics:
        if m.trend is not None and len(m.trend) >= 2:
            a, b = m.trend.iloc[0], m.trend.iloc[-1]
            ch = (b / a - 1) * 100 if a else None
            res.sentences.append(f"{area}의 {m.name} 월별 변화: {m.trend.index[0]} {fmt(a, m.unit, m.digits)} → {m.trend.index[-1]} "
                                 f"{fmt(b, m.unit, m.digits)}" + (f" ({ch:+.1f}%)" if ch is not None else "")
                                 + f", 가장 높은 달 {m.trend.idxmax()}. (허브 {m.measures[0].dataset})")
        res.limits += [n for n in m.notes if n not in res.limits]
    res.limits.append("판정(높음·보통·낮음)은 제주 읍면동 사이의 상대 위치이며, 좋고 나쁨이나 창업 여부를 정해 주는 결과가 아닙니다.")
    res.notes_top = concept_lines(res)
    res.warnings = stale_warnings(res)
    return res


# ---------------- 결론·해설·경고 ----------------

def _asked_ok(res: Result) -> list:
    ms = [m for m in res.metrics if not m.reason and getattr(m, "asked", False)]
    return ms or [m for m in res.metrics if not m.reason]


def _ga(word: str) -> str:
    return f"{word}{josa(word, '이가')}"


def _f(v, m) -> str:
    """결론 문장용 숫자: '(지표)' 같은 단위 꼬리는 빼고(아래 해설이 설명), 금액은 억·만으로,
    '곳(방문 1만당)'은 '방문 1만당 3.36곳'으로."""
    mt = re.fullmatch(r"(\S+)\((.+)\)", m.unit or "")
    if mt:
        return f"{mt.group(2)} {fmt(v, '', m.digits)}{mt.group(1)}"
    return fmt(v, "" if m.unit == "(지표)" else m.unit, m.digits if m.digits else 0)


def _nm(m) -> str:
    """결론 문장용 지표 이름: 괄호 설명은 빼고(카드에 전체 이름이 있음)."""
    return re.sub(r"\s*\([^)]*\)", "", m.name).strip() or m.name


def _per(m) -> str:
    """결론 문장용 기준 시점: '2025-09-18 기준 ÷ 2025-09' 같은 표기를 가장 늦은 달 하나로."""
    ds = re.findall(r"\d{4}-\d{2}", m.period or "")
    return f"{max(ds)} 기준" if ds else (m.period or "")


def lead_for(res: Result, slots: dict, area: str | None) -> str:
    """질문 유형(모델 해석의 analysis)과 결과 모양으로 결론 한 줄을 고른다. 숫자는 모두 계산 결과에서.
    결론에는 질문한 지표만 쓴다(관점 지표는 '함께 볼 지표'에서 보여 준다)."""
    ms = _asked_ok(res)
    if not ms:
        return ""
    analysis = slots.get("analysis")
    m0 = ms[0]
    if res.cross:
        c = res.cross
        hits = ", ".join(c["hits"][:8]) + (f" 외 {len(c['hits']) - 8}곳" if len(c["hits"]) > 8 else "")
        return (f"{c['desc']}: {hits or '없음'} ({len(c['hits'])}곳). "
                "어디가 좋은지는 정해 드리지 않고 조건에 맞는 곳을 보여 드립니다.")
    # 추이
    tm = next((m for m in ms if m.trend is not None and len(m.trend) >= 2), None)
    if analysis == "trend" and tm is not None:
        a, b = float(tm.trend.iloc[0]), float(tm.trend.iloc[-1])
        ch = (b / a - 1) if a else None
        word = ("늘었습니다" if ch is not None and ch >= TREND_BAND else
                "줄었습니다" if ch is not None and ch <= -TREND_BAND else "큰 변화가 없습니다")
        s = (f"{word} — {area} {_nm(tm)} {tm.trend.index[0]} {_f(a, tm)} → {tm.trend.index[-1]} {_f(b, tm)}"
             + (f" ({ch * 100:+.1f}%)" if ch is not None else "") + ".")
        miss = getattr(tm, "missing", [])
        if miss:
            s += f" {', '.join(miss)}{josa(miss[-1])} 자료가 없어 빠졌습니다."
        return s
    # 비교(질문 지표끼리만)
    if len(res.places) >= 2:
        wins = []
        for m in ms:
            v = m.values.reindex(res.places).dropna()
            if len(v) >= 2:
                wins.append((m, v.idxmax(), v))
        if wins:
            m, top, v = wins[0]
            s = f"{_ga(top)} 더 높습니다 — {_nm(m)} " + " vs ".join(f"{a} {_f(float(x), m)}" for a, x in v.items()) + f" ({_per(m)})."
            other = [(mm, t) for mm, t, _ in wins[1:] if t != top][:2]
            if other:
                s += " 다만 " + ", ".join(f"{_nm(mm)}{josa(_nm(mm))} {_ga(t)}" for mm, t in other) + " 더 높습니다."
            return s
        missing = [p for p in res.places if p not in m0.values.dropna().index]
        if missing:
            return f"{_nm(m0)}: {', '.join(missing)} 값이 이 자료에 없어 비교할 수 없습니다 ({_per(m0)})."
    # 순위 / 지역 없음
    if not area or analysis == "rank":
        v = m0.values.dropna().sort_values(ascending=False)
        if len(v) >= 3:
            s = (f"{_nm(m0)}{josa(_nm(m0), '이가')} 가장 높은 곳은 {v.index[0]}({_f(float(v.iloc[0]), m0)})이고, "
                 f"이어서 {v.index[1]}, {v.index[2]} 순입니다 ({_per(m0)}).")
            if area and area in v.index:
                s += f" {area}{josa(area)} {list(v.index).index(area) + 1}위입니다."
            return s
        if m0.scalar is not None and not area:
            return f"제주 전체 {_nm(m0)}{josa(_nm(m0))} {_f(m0.scalar, m0)}입니다 ({_per(m0)})."
    # 개수·비율·단순 조회: 대상 지역 값 + 제주 안 위치(짧게)
    row = next(r for r in res.rows if r["id"] == m0.id)
    if row["대상 값"] is None:
        return (sentence(row, m0) or "").split(" (허브")[0]
    val = _f(row["대상 값"], m0)
    s = f"{area} {_nm(m0)}{josa(_nm(m0))} {val}입니다"
    if row["순위"]:
        s += f" — 제주 {row['비교 수']}곳 중 {row['순위']}위({VERDICT.get(row['판정'], row['판정'])})"
    return s + f" ({_per(m0)})."


def _goal_metric(res: Result, concept: str):
    # 질문 지표를 먼저, 없으면 관점 지표에서. 점포 수 조건은 밀도(방문지표 1만당)를 쓴다 —
    # 점포 수 그대로는 큰 동네일수록 많아 '경쟁 적은 곳'이 작은 동네로만 몰리기 때문.
    ok = [m for m in res.metrics if not m.reason and m.values.notna().sum() >= MIN_COMPARE]
    ms = [m for m in ok if getattr(m, "concepts", [None])[0] == concept]
    if concept == "점포수":
        ms.sort(key=lambda m: (m.kind != "ratio", not getattr(m, "asked", False)))
    else:  # 그 밖의 조건은 질문 지표 그대로(외국인 방문지표 → 외국인/내국인 비율로 바꾸지 않음)
        ms.sort(key=lambda m: (not getattr(m, "asked", False), m.kind == "ratio"))
    return ms[0] if ms else None


def cross_table(res: Result, goals: list[dict]) -> dict | None:
    """조건 2개(모델이 준 방향 high/low)를 43곳에 함께 적용한다. 첫 조건은 상·하위 25%, 둘째 조건은 중앙값 기준."""
    if len(goals) < 2:
        return None
    a, b = _goal_metric(res, goals[0]["concept"]), _goal_metric(res, goals[1]["concept"])
    if a is None or b is None or a is b:
        return None
    df = pd.concat([a.values.rename("A"), b.values.rename("B")], axis=1).dropna()
    if len(df) < MIN_COMPARE:
        return None
    qa_hi, qa_lo, mb = df["A"].quantile(1 - QUANTILE), df["A"].quantile(QUANTILE), df["B"].median()
    df["A구간"] = ["상위 25%" if x >= qa_hi else "하위 25%" if x <= qa_lo else "중간" for x in df["A"]]
    df["B구간"] = ["중앙값 이상" if x >= mb else "중앙값 이하" for x in df["B"]]
    wa, wb = goals[0]["want"], goals[1]["want"]
    ok_a = df["A구간"] == ("상위 25%" if wa == "high" else "하위 25%")
    ok_b = df["B"] >= mb if wb == "high" else df["B"] <= mb
    hit = df[ok_a & ok_b].sort_values("A", ascending=(wa == "low"))
    table = pd.crosstab(df["A구간"], df["B구간"]).reindex(index=["상위 25%", "중간", "하위 25%"],
                                                          columns=["중앙값 이상", "중앙값 이하"], fill_value=0)
    table.index.name, table.columns.name = a.name, b.name
    desc = (f"{a.name} {'상위' if wa == 'high' else '하위'} 25%이면서 "
            f"{b.name}{josa(b.name, '이가')} 중앙값 {'이상' if wb == 'high' else '이하'}인 곳")
    return {"a": a.id, "b": b.id, "a_name": a.name, "b_name": b.name, "want": (wa, wb), "hits": list(hit.index),
            "table": table, "frame": df, "desc": desc, "cut": {"a_hi": qa_hi, "a_lo": qa_lo, "b_med": mb}}


def concept_lines(res: Result) -> list[str]:
    """계산된 질문 지표의 개념마다 해설 한 줄. 질문에 일상 말(when_words)이 있으면 '○○은 △△로 계산' 문장을 앞에 붙인다."""
    notes, out, seen = concept_notes(), [], set()
    for m in _asked_ok(res):
        for c in getattr(m, "concepts", []):
            n = notes.get(c)
            if not n or c in seen:
                continue
            seen.add(c)
            words = [w for w in n.get("when_words", []) if w in (res.question or "")]
            pre = f"'{words[0]}'{josa(words[0])} {n.get('label', c)}{ro(n.get('label', c))} 계산했습니다. " if words else ""
            out.append(pre + n["note"])
    return out


def _months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def stale_warnings(res: Result, today: dt.date | None = None) -> list[str]:
    today = today or dt.date.today()
    out = []
    for m in _asked_ok(res):
        end = getattr(m, "end", None)
        if not end:
            continue
        try:
            d = dt.date.fromisoformat(end[:10])
        except ValueError:
            continue
        if _months_between(d, today) >= STALE_MONTHS:
            w = f"⚠ {m.name} 값은 {end[:7]} 자료입니다. 그 뒤 자료는 허브에 없습니다."
            if w not in out:
                out.append(w)
    return out
