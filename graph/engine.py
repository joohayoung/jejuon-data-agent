"""범용 계산 엔진: 개념(무엇을 잴지) → 지식 그래프에서 자료·컬럼 선택 → 템플릿 계획 → 검증 → 43개 읍면동 계산.

원칙(LLM은 숫자를 만들지 않는다)
- 자료·컬럼·집계 방법은 그래프 메타데이터(역할·단위·공간 단위·주의사항)로 코드가 정한다.
- 단위가 '지표'면 여러 날을 더하지 않고 일평균, 측정 컬럼이 없는 개체 목록은 행 수(count).
- 비율은 두 자료가 같은 자료이거나 그래프에서 결합 가능(JOINABLE)할 때만 계산한다.
- denominator_scope(예: 746 매장수 = 업종 전체 값)가 있는 컬럼은 측정값으로 쓰지 않는다.
- 지역 순위 판정은 43개 읍면동 전체를 계산해서 한다. 전체를 못 받으면 요청 지역만 계산하고 판정은 보류한다.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from graph import access as da
from graph.kg import KG

ROOT = Path(__file__).resolve().parents[1]
LEVEL_ORDER = ["좌표", "주소", "법정동", "읍면동", "시군구", "시도"]
SKIP_ROLES = {"관리용", "식별자"}
SENSITIVE = re.compile(r"상호|사업장명|업소명|업체명|companyName|placeName|전화|연락처", re.I)


# ---------------- 공용 ----------------

@lru_cache(maxsize=1)
def kg() -> KG:
    return KG()


@lru_cache(maxsize=1)
def regions() -> dict:
    return yaml.safe_load((ROOT / "data" / "regions.yaml").read_text(encoding="utf-8"))["regions"]


def all_areas() -> list[str]:
    return sorted(regions())


def city_of(area: str) -> str:
    return regions().get(area, {}).get("시", "")


@lru_cache(maxsize=1)
def legal_map() -> dict[str, list[tuple[str, float]]]:
    """법정동 이름 → [(행정동, 비중)] (그래프 MAPS_TO, 793 원자료로 계산된 비중)."""
    g = kg()
    m = defaultdict(list)
    for nid, n in g.n.items():
        if n["type"] == "Place" and n.get("level") == "법정동":
            for e in g.out[nid]:
                if e["type"] == "MAPS_TO":
                    m[n["name"]].append((g.n[e["dst"]]["name"], float(e.get("share") or 1.0)))
    return dict(m)


@lru_cache(maxsize=1)
def ri_map() -> dict[str, str]:
    """리 이름 → 읍면(regions.yaml)."""
    out = {}
    for adm, r in regions().items():
        for ri in r.get("리") or []:
            out.setdefault(ri, adm)
    return out


def to_admin(value, grain: str) -> list[tuple[str, float]]:
    """원자료의 지역 값 → [(행정동, 비중)]. 맞출 수 없으면 []."""
    v = str(value or "").strip()
    if not v:
        return []
    areas = regions()
    if grain == "읍면동":
        return [(v, 1.0)] if v in areas else []
    if grain == "법정동":
        if v in legal_map():
            return legal_map()[v]
        return [(v, 1.0)] if v in areas else []
    if grain == "주소":
        toks = re.sub(r"\([^)]*\)|[,()·]", " ", v).split()  # '서홍동(중앙로타리 인근)' → '서홍동'
        toks = [re.sub(r"(인근|일대|부근)$", "", x) for x in toks]
        for t in toks:
            if t in areas:
                return [(t, 1.0)]
        for t in toks:
            if t in legal_map():
                # 주소는 한 지점이므로 비중으로 나누지 않고, 비중이 가장 큰 행정동 하나로 본다(애매하면 버림)
                adm, share = max(legal_map()[t], key=lambda x: x[1])
                return [(adm, 1.0)] if share >= 0.5 else []
        for t in toks:
            if t in ri_map():
                return [(ri_map()[t], 1.0)]
    return []


# ---------------- 계획 단위 ----------------

@dataclass
class Measure:
    """개념 하나를 잴 계획(자료·컬럼·집계)."""
    concept: str
    dataset: int
    title: str
    access: str
    op: str                      # count | sum | mean | daily_mean
    column: str | None
    unit: str
    place_column: str | None
    place_grain: str | None
    time_column: str | None
    filters: dict = field(default_factory=dict)     # {컬럼: [값]}
    snapshot: bool = False
    period: tuple[str, str] | None = None
    data_end: str | None = None
    notes: list = field(default_factory=list)       # 화면에 보여 줄 설명
    dev_notes: list = field(default_factory=list)   # 그래프 컬럼 메모(개발용, '분석 과정 기록'에만)
    data_start: str | None = None
    data_key: str | None = None
    api_params: list = field(default_factory=list)

    @property
    def via(self) -> str:
        return "API" if "API" in self.access and self.data_key else "파일"


@dataclass
class Metric:
    """화면·판정에 쓰는 결과 한 개(B의 IndicatorResult와 같은 역할)."""
    id: str
    name: str
    unit: str
    values: pd.Series                 # index=행정동
    period: str = ""
    sources: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    reason: str | None = None         # 계산 보류 사유
    scalar: float | None = None       # 제주 전체 값(지역 없음)
    kind: str = ""                    # count/sum/mean/daily_mean/ratio
    complete: bool = True             # 43개 동 전체를 계산했는가
    measures: list = field(default_factory=list)
    joinable: dict | None = None
    trend: pd.DataFrame | None = None
    breakdown: pd.Series | None = None
    digits: int = 0


# ---------------- 자료 선택 ----------------

def _cols(did: str):
    g = kg()
    return [c for _, c in g.keys(did)[2]]


def _snapshot(d: dict) -> bool:
    end = d.get("auto_update_verified_end") or d.get("period_end")
    return bool(d.get("period_start")) and d.get("period_start") == end


def _available(d: dict) -> bool:
    return ("API" in str(d.get("access")) and bool(d.get("data_key"))) or da.has_file(d["hub_id"])


@lru_cache(maxsize=1)
def industry_map() -> dict:
    return yaml.safe_load((ROOT / "data" / "industries.yaml").read_text(encoding="utf-8"))


# 업종 대응표(data/industries.yaml)의 데이터 키 → (허브 ID, 컬럼)
INDUSTRY_COLUMNS = {"store": (793, "상권업종소분류명"), "card_emd": (746, "업종명"), "restaurant": (780, "업종구분소분류")}


def industry_key(text: str | None) -> str | None:
    if not text:
        return None
    t = text.replace(" ", "")
    for k, v in industry_map().items():
        if not isinstance(v, dict):
            continue
        if t == k.replace(" ", "") or t in [a.replace(" ", "") for a in v.get("aliases", [])]:
            return k
    return None


def _filter_values(d: dict, col: dict, value: str) -> list[str]:
    """질문의 구분값(예: 카페)을 이 컬럼의 실제 값으로. 정확히 같은 값만(비슷한 값은 더하지 않는다)."""
    hid = d["hub_id"]
    key = industry_key(value)
    if key:
        spec = industry_map()[key]
        for dkey, (h, c) in INDUSTRY_COLUMNS.items():
            if h == hid and c == col["name"]:
                vals = list((spec.get(dkey) or {}).values())
                flat = [x for v in vals for x in (v if isinstance(v, list) else [v])]
                if flat:
                    return flat
    if "API" in str(d.get("access")) and not da.has_file(hid):
        ex = str(col.get("example") or "")
        return [value] if value == ex.strip() else []
    try:
        got = da.file_values(hid, col["name"], like=value, top=50)
    except da.DataAccessError:
        return []
    return [g for g in got if str(g).strip() == value]


def _place_column(cols: list[dict], level: str | None):
    if level is None:
        return None, None
    best = None
    for c in cols:
        if c["role"] != "공간키" or c.get("grain") not in LEVEL_ORDER:
            continue
        if SENSITIVE.search(c["name"]):
            continue
        g = c["grain"]
        if g in ("읍면동", "법정동", "주소"):
            rank = {"읍면동": 0, "법정동": 1, "주소": 2}[g]
            if re.search(r"(코드|code|Code|CD|cd)$", c["name"]):
                rank += 5  # 코드 값(예: 5011010400)은 이름으로 맞출 수 없어 가장 뒤로
            if best is None or rank < best[0]:
                best = (rank, c)
    return (best[1]["name"], best[1]["grain"]) if best else (None, None)


def choose_measure(concept: str, filters: dict[str, str], level: str | None = "읍면동",
                   period: tuple[str, str] | None = None, prefer: list[int] | None = None):
    """(Measure 또는 None, 채택 후보, 제외 {허브ID: 사유})."""
    g = kg()
    found = g.find_datasets([concept], level, period, top=25).get(concept, {})
    rejected = {}
    if found.get("error"):
        return None, [], {}
    for x in found.get("excluded", []):
        rejected[g.n[x["id"]]["hub_id"]] = "; ".join(x["excluded"])
    cands = list(found.get("candidates", []))
    if prefer:
        cands.sort(key=lambda x: g.n[x["id"]]["hub_id"] not in prefer)
    for x in cands:
        d = g.n[x["id"]]
        hid = d["hub_id"]
        if not _available(d):
            rejected[hid] = "운영 시 센터 서버 데이터로 계산(데모 환경에 원자료 없음)"
            continue
        cols = _cols(x["id"])
        if x.get("caution"):
            rejected[hid] = f"측정 범위 주의: {x['caution']}"
            continue
        mcols = [c for c in cols if c["role"] == "측정값" and c.get("concept") == concept
                 and not c.get("denominator_scope") and "지역 분모 불가" not in str(c.get("note", ""))]
        snap = _snapshot(d)
        time_col = next((c["name"] for c in cols if c["role"] == "시간키" and c.get("grain") == "일"), None) \
            or next((c["name"] for c in cols if c["role"] == "시간키"), None)
        if mcols:
            mc = mcols[0]
            unit = mc.get("unit") or ""
            if unit == "지표" or (time_col and not snap and unit in ("명", "")):
                op = "daily_mean" if (time_col and any(c["name"] == time_col and c.get("grain") == "일" for c in cols)) else "mean"
            elif re.search(r"%|율|지수|℃|㎜|mm", unit):
                op = "mean"
            else:
                op = "sum"
            column = mc["name"]
        else:
            if not (snap and concept.endswith("수")):
                rejected[hid] = "이 개념을 재는 컬럼이 없음"
                continue
            op, column, unit = "count", None, "개"
        pcol, pgrain = _place_column(cols, level)
        if level and not pcol:
            rejected[hid] = "읍면동으로 맞출 수 있는 지역 컬럼 없음"
            continue
        fcols, ok = {}, True
        for dim, val in (filters or {}).items():
            cands_c = [c for c in cols if c["role"] == "구분값" and c.get("concept") == dim and not SENSITIVE.search(c["name"])]
            hit = None
            for c in sorted(cands_c, key=lambda c: c["name"] != "상권업종소분류명"):
                vals = _filter_values(d, c, val)
                if vals:
                    hit = (c["name"], vals)
                    break
            if not hit:
                rejected[hid] = f"'{val}'({dim}) 값으로 나눌 수 있는 컬럼 없음"
                ok = False
                break
            fcols[hit[0]] = hit[1]
        if not ok:
            continue
        end = d.get("auto_update_verified_end") or d.get("period_end")
        notes, dev_notes = [], []
        for c in cols:
            if c["name"] in ([column] if column else []) + ([pcol] if pcol else []) and c.get("note"):
                dev_notes.append(f"{c['name']}: {c['note']}")
        if pgrain == "법정동":
            notes.append("법정동 값을 행정동으로 변환(그래프의 법정동→행정동 비중 사용)")
        if pgrain == "주소":
            notes.append("주소에서 읍면동을 찾아 셈(주소가 불완전한 행은 제외)")
        m = Measure(concept=concept, dataset=hid, title=d["title"], access=str(d["access"]), op=op, column=column,
                    unit=unit, place_column=pcol, place_grain=pgrain, time_column=time_col if op in ("daily_mean",) else time_col,
                    filters=fcols, snapshot=snap, data_end=str(end)[:10] if end else None, notes=notes,
                    dev_notes=dev_notes, data_start=str(d.get("period_start"))[:10] if d.get("period_start") else None,
                    data_key=d.get("data_key"), api_params=d.get("api_params") or [])
        return m, cands, rejected
    return None, cands, rejected


def default_period(m: Measure, asked: tuple[str, str] | None, anchor: str | None = None) -> tuple[str, str] | None:
    """기간: 질문 기간 → (스냅샷과 함께면) 스냅샷 날짜의 달 → 자료 최신 달."""
    if m.snapshot:
        return (m.data_end, m.data_end) if m.data_end else None
    if asked:
        end = asked[1]
        if m.data_end and end > m.data_end:
            end = m.data_end  # 자료가 아직 없는 뒷부분은 자른다(화면에 안내)
        return (asked[0], end) if asked[0] <= end else asked
    ref = anchor or m.data_end
    if not ref:
        return None
    # 기준일(다른 자료의 시점)이 이 자료 기간 밖이면 기준일을 버리고 이 자료의 최신 달을 쓴다
    if anchor and m.data_end and (ref[:10] > m.data_end or (m.data_start and ref[:10] < m.data_start)):
        ref = m.data_end
    d = dt.date.fromisoformat(ref[:10])
    start = d.replace(day=1)
    nxt = (start + dt.timedelta(days=32)).replace(day=1)
    end = min(nxt - dt.timedelta(days=1), dt.date.fromisoformat(m.data_end[:10]) if m.data_end else nxt)
    return start.isoformat(), end.isoformat()


# ---------------- 검증 ----------------

def validate(m: Measure, period: tuple[str, str] | None) -> list[str]:
    errs = []
    if m.op not in ("count", "sum", "mean", "daily_mean"):
        errs.append(f"지원하지 않는 계산({m.op})")
    if m.unit == "지표" and m.op == "sum" and period and period[0] != period[1]:
        errs.append(f"{m.column}는 단위가 '지표'라 여러 날을 더할 수 없습니다(일평균으로 계산해야 함).")
    if m.op == "daily_mean" and not m.time_column:
        errs.append("일평균을 낼 날짜 컬럼이 없습니다.")
    if period and not m.snapshot and m.data_end and period[0] > m.data_end:
        errs.append(f"요청 기간({period[0]}~)이 자료 최신일({m.data_end}) 뒤입니다.")
    if m.column and SENSITIVE.search(m.column):
        errs.append("개인·상호 정보 컬럼은 계산에 쓰지 않습니다.")
    return errs


# ---------------- 조회 ----------------

def _api_calls(m: Measure, period, place: str | None):
    params = {p["name"].strip(): p for p in m.api_params}
    base = {}
    if period and not m.snapshot:
        if "startDate" in params:
            f = da.date_format(m.api_params, "startDate")
            base["startDate"] = dt.date.fromisoformat(period[0]).strftime(f)
            base["endDate"] = dt.date.fromisoformat(period[1]).strftime(f)
            calls = [base]
        elif "searchDate" in params:
            f = da.date_format(m.api_params, "searchDate")
            calls = [dict(base, searchDate=x) for x in da.daterange(period[0], period[1], f)[:62]]
        else:
            calls = [base]
    else:
        calls = [base]
    if place and "emd" in params:
        calls = [dict(c, emd=place) for c in calls]
    return calls


def fetch_rows(m: Measure, period, places: list[str] | None, offline: bool = False):
    """(행 목록, 전체 동을 받았는가, 수집 시각).
    API 자료에 읍면동 변수(emd)가 있으면 43개 읍면동을 하나씩 받는다(응답이 작고 캐시가 지역별로 남아 재사용이 쉽다)."""
    need = [c for c in [m.place_column, m.column, m.time_column, *m.filters] if c]
    if m.via == "파일":
        rows = da.file_query(m.dataset, list(dict.fromkeys(need)), m.filters or None)
        return rows, True, (da.file_loaded(m.dataset) or {}).get("files")
    has_emd = any(p["name"].strip() == "emd" for p in m.api_params)
    rows, missing, fetched, first_err = [], [], None, None
    # 1) 읍면동 변수 없이 한 번에(43곳 전체) — 저장된 응답이 있으면 바로 씀
    for off in ([offline] if offline else [False, True]):
        try:
            got = []
            for c in _api_calls(m, period, None):
                r, _, fetched = da.hub_fetch(m.dataset, m.data_key, c, offline=off)
                got += r
            for col, vs in m.filters.items():
                vs2 = {str(v).strip() for v in vs}
                got = [r for r in got if str(r.get(col, "")).strip() in vs2]
            return got, True, fetched
        except da.DataAccessError as e:
            first_err = e
            if not off and ("쿼터" in str(e) or "연결" in str(e) or "키가 없" in str(e)):
                offline = True
    # 2) 안 되면 읍면동별로(질문 지역 먼저)
    order = list(dict.fromkeys((places or []) + all_areas())) if has_emd else []
    for area in order:
        got = None
        for off in ([offline] if offline else [False, True]):
            try:
                got = []
                for c in _api_calls(m, period, area):
                    r, _, fetched = da.hub_fetch(m.dataset, m.data_key, c, offline=off)
                    got += r
                break
            except da.DataAccessError as e:
                got = None
                first_err = first_err or e
                if not off and ("쿼터" in str(e) or "연결" in str(e) or "키가 없" in str(e)):
                    offline = True  # 더 부르지 않고 저장된 것만 쓴다
        if got is None:
            missing.append(area)
        else:
            rows += got
    if not rows:
        raise first_err or da.DataAccessError("자료를 받지 못했습니다.")
    complete = not missing
    for col, vs in m.filters.items():
        vs = {str(v).strip() for v in vs}
        rows = [r for r in rows if str(r.get(col, "")).strip() in vs]
    return rows, complete, fetched


def aggregate(m: Measure, rows: list[dict], level: str | None = "읍면동") -> tuple[pd.Series, float | None, dict]:
    """→ (행정동별 값, 제주 전체 값, 정보). level None이면 제주 전체 값만."""
    acc = defaultdict(float)
    n = defaultdict(float)
    days = defaultdict(lambda: defaultdict(float))
    unmatched = 0
    for r in rows:
        if m.op == "count":
            val = 1.0
        else:
            val = r.get(m.column)
            if isinstance(val, str):
                val = da.num(val)
            if not isinstance(val, (int, float)) or (isinstance(val, float) and math.isnan(val)):
                continue
        if level and m.place_column:
            targets = to_admin(r.get(m.place_column), m.place_grain)
            if not targets:
                unmatched += 1
                continue
        else:
            targets = [("제주 전체", 1.0)]
        for area, w in targets:
            if m.op == "daily_mean":
                days[area][str(r.get(m.time_column))] += val * w
            else:
                acc[area] += val * w
                n[area] += w
    out = {}
    keys = set(acc) | set(days)
    for a in keys:
        if m.op == "daily_mean":
            dd = days[a]
            out[a] = sum(dd.values()) / len(dd) if dd else math.nan
        elif m.op == "mean":
            out[a] = acc[a] / n[a] if n[a] else math.nan
        else:
            out[a] = acc[a]
    info = {"unmatched": unmatched, "rows": len(rows)}
    if not level:
        return pd.Series(dtype=float), out.get("제주 전체"), info
    s = pd.Series(out, dtype=float).reindex(all_areas())
    if m.op == "count":
        s = s.fillna(0.0) if s.notna().any() else s
    if m.op == "daily_mean":
        alld = defaultdict(float)
        for a, dd in days.items():
            for k, v in dd.items():
                alld[k] += v
        total = sum(alld.values()) / len(alld) if alld else None
    elif m.op == "mean":
        total = float(s.mean()) if s.notna().any() else None
    else:
        total = float(s.sum()) if s.notna().any() else None
    return s, total, info


def period_label(m: Measure, period) -> str:
    if m.snapshot:
        return f"{m.data_end} 기준"
    if not period:
        return ""
    a, b = period
    if a[:7] == b[:7] and a[8:] == "01":
        return a[:7]
    return f"{a} ~ {b}" if a != b else a


def compute(m: Measure, period, places: list[str] | None, level: str | None = "읍면동", offline: bool = False):
    """→ (값 Series, 제주 전체, 정보)."""
    rows, complete, fetched = fetch_rows(m, period, places, offline=offline)
    s, total, info = aggregate(m, rows, level)
    if level and m.op == "count" and not complete:
        s = s.where(s.index.isin(places or []))
    info.update(complete=complete, fetched=fetched)
    return s, total, info


def joinable(a: int, b: int) -> dict | None:
    if a == b:
        return {"space_key": "같은 자료", "overlap": ["", ""]}
    e = kg().joinable(f"ds:{a}", f"ds:{b}")
    return e


def expected_months(end: str, months: int) -> list[str]:
    d = dt.date.fromisoformat(end[:10])
    y, mo, out = d.year, d.month, []
    for _ in range(months):
        out.append(f"{y:04d}-{mo:02d}")
        y, mo = (y, mo - 1) if mo > 1 else (y - 1, 12)
    return sorted(out)


def monthly_trend(m: Measure, place: str, months: int = 6, end: str | None = None, offline: bool = False) -> pd.Series:
    """한 지역의 최근 n개월 월별 값(시계열 API·파일 자료). 지역 하나만 받으므로 호출이 적다."""
    if m.snapshot or not m.time_column:
        return pd.Series(dtype=float)
    last = dt.date.fromisoformat((end or m.data_end)[:10])
    out = {}
    y, mo = last.year, last.month
    for _ in range(months):
        start = dt.date(y, mo, 1)
        nxt = (start + dt.timedelta(days=32)).replace(day=1)
        stop = min(nxt - dt.timedelta(days=1), last)
        per = (start.isoformat(), stop.isoformat())
        try:
            if m.via == "파일":
                rows, _, _ = fetch_rows(m, per, [place], offline=offline)
                rows = [r for r in rows if str(r.get(m.time_column, ""))[:7].replace("-", "") in (start.strftime("%Y%m"), start.strftime("%Y-%m").replace("-", ""))]
            else:
                rows = []
                for c in _api_calls(m, per, place):
                    r, _, _ = da.hub_fetch(m.dataset, m.data_key, c, offline=offline)
                    rows += r
            s, _, _ = aggregate(m, rows, "읍면동")
            if place in s.index and pd.notna(s[place]):
                out[start.strftime("%Y-%m")] = float(s[place])
        except da.DataAccessError:
            pass
        y, mo = (y, mo - 1) if mo > 1 else (y - 1, 12)
    return pd.Series(out).sort_index()
