"""질문 해석: 로컬 LLM이 정해진 어휘(검수 개념 162개) 안에서 슬롯을 뽑고, 코드 가드가 고친다.

- LLM 출력은 JSON 스키마로 강제(개념은 enum) → 어휘 밖 단어는 나올 수 없다.
- 가드는 지우기만 한다: 질문에 없는 날짜·지명, 질문에 낱말로 나오지 않은 구분값. 비율이면 분자·분모 형식만 맞춘다.
- 코드는 질문에서 낱말을 따로 뽑지 않는다. 모델이 꺼져 있거나 실패하면 해석하지 않고 그 사실을 알린다.
"""
from __future__ import annotations

import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

from graph import engine as en

ROOT = Path(__file__).resolve().parents[1]
DATE_HINT = re.compile(r"\d{4}\s*년|\d{4}[.-]\d{1,2}|\d{1,2}\s*월\s*\d{1,2}\s*일|\d{1,2}\s*월")


# ---------------- 어휘 ----------------

@lru_cache(maxsize=1)
def vocab() -> dict:
    g = en.kg()
    meas, dims, syn = [], [], {}
    for v in g.n.values():
        if v["type"] != "Concept" or v.get("status") != "어휘":
            continue
        (meas if v["kind"] == "측정값" else dims).append(v["name"])
        for s in [v["name"], *(v.get("synonyms") or [])]:
            s = str(s).replace(" ", "")
            if len(s) >= 2 and re.search(r"[가-힣]", s) and s not in SYN_STOP:
                syn.setdefault(s, (v["name"], v["kind"]))
    return {"measures": sorted(meas), "dims": sorted(dims), "syn": syn}


SYN_STOP = {"내국인", "도민", "주민", "외국인", "개별", "단체", "도심", "읍면", "인구"}  # 너무 일반적인 말은 동의어로 쓰지 않음


# ---------------- 스키마 ----------------

def _schema():
    V = vocab()
    Measure = Literal[tuple(V["measures"])]
    Dim = Literal[tuple(V["dims"])]

    class GFilter(BaseModel):
        concept: Dim
        value: str

    class GRatio(BaseModel):
        numerator: Measure
        denominator: Measure
        scale: int

    class GPeriod(BaseModel):
        start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
        end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    class GraphSlots(BaseModel):
        # 모든 항목을 필수로 둔다. 기본값을 주면 JSON 스키마에서 '선택 항목'이 되어,
        # 작은 모델이 places·concepts를 통째로 빼고 {"analysis": ...}만 내는 일이 생긴다.
        places: list[str] = Field(max_length=4)
        concepts: list[Measure] = Field(max_length=3)  # 잴 대상이 없는 질문이면 [] (억지로 고르지 않게)
        filters: list[GFilter] = Field(max_length=3)
        period: Optional[GPeriod]
        analysis: Literal["count", "sum", "mean", "ratio", "compare", "trend", "share", "rank", "lookup"]
        ratio: Optional[GRatio]
        unsupported: str

    return GraphSlots


def register_schema():
    from agent.schemas import SCHEMAS
    SCHEMAS.setdefault("graph_interpret", _schema())


# ---------------- 지명 ----------------

@lru_cache(maxsize=1)
def _regions() -> dict:
    return yaml.safe_load((ROOT / "data" / "regions.yaml").read_text(encoding="utf-8"))["regions"]


def find_places(text: str) -> tuple[list[str], list[str]]:
    """(질문에서 찾은 행정동 목록(나온 순서), 모호한 표현)."""
    t = text.replace(" ", "")
    hits = []
    for adm, r in _regions().items():
        for al in sorted(set(r["aliases"] + [adm]), key=len, reverse=True):
            if len(al) >= 2 and al in t:
                hits.append((t.index(al), len(al), adm, al))
                break
    hits.sort()
    out, used = [], []
    for pos, ln, adm, al in hits:
        if any(pos >= p and pos + ln <= p + l2 and (p, l2) != (pos, ln) for p, l2 in used):
            continue
        if adm not in out:
            out.append(adm)
            used.append((pos, ln))
    return out, []


def normalize_place(word: str) -> tuple[str | None, str | None]:
    """(행정동, 되묻기 후보)."""
    w = word.replace(" ", "")
    for adm, r in _regions().items():
        if w == adm or w in r["aliases"]:
            return adm, None
    found, _ = find_places(w)
    if len(found) == 1:
        return found[0], None
    k, guess = en.kg().place(w)
    if k:
        name = en.kg().n[k]["name"]
        return (name if name in _regions() else None), None
    return None, guess


PARTICLES = ("", "이", "가", "은", "는", "을", "를", "에", "에서", "의", "도", "만", "랑", "이랑", "과", "와", "로", "으로",
             "집", "들", "은요", "는요", "이요", "요", "이에요", "예요", "가게", "점")


def _word_in(q: str, word: str) -> bool:
    """word가 질문에 '낱말'로 나오는가(뒤에 조사·'집' 정도만 허용). '바꿀까' 속 '바'는 아니다."""
    toks = re.findall(r"[가-힣A-Za-z0-9]+", q)
    w = word.replace(" ", "")
    if " " in word.strip():
        return word.strip() in q
    return any(tk == w or (tk.startswith(w) and tk[len(w):] in PARTICLES) for tk in toks)


# ---------------- LLM 해석 + 가드 ----------------

@lru_cache(maxsize=1)
def measures_with_synonyms() -> str:
    """측정값 이름 + 한글 동의어 2개까지(모델이 일상 말을 개념에 맞추도록). 약 1,900자."""
    out = []
    for v in sorted((v for v in en.kg().n.values() if v["type"] == "Concept" and v.get("status") == "어휘"
                     and v["kind"] == "측정값"), key=lambda v: v["name"]):
        syn = [s for s in (v.get("synonyms") or []) if re.search(r"[가-힣]", s) and s != v["name"]][:2]
        out.append(v["name"] + (f"({'·'.join(syn)})" if syn else ""))
    return ", ".join(out)


def _prompt(q: str) -> tuple[str, str]:
    V = vocab()
    text = (Path(__file__).resolve().parents[1] / "agent" / "prompts" / "graph_interpret.md").read_text(encoding="utf-8")
    system, user = text.split("### user", 1)
    system = system.replace("### system", "").strip().replace("{measures}", measures_with_synonyms()).replace("{dims}", ", ".join(V["dims"]))
    return system, user.strip().replace("{question}", q)


def interpret(q: str) -> tuple[dict, dict]:
    """(슬롯, 기록). 해석은 로컬 모델만 한다. 기록: by, guards, stats, ask(되묻기·실패 안내)."""
    from agent import llm
    t0 = time.time()
    rec = {"by": "모델", "guards": [], "stats": {}, "ask": None}
    empty = {"places": [], "concepts": [], "filters": {}, "period": None, "analysis": "lookup", "ratio": None, "unsupported": ""}
    if llm.llm_mode() == "off":
        rec["ask"] = "질문 해석에 쓰는 로컬 모델이 꺼져 있습니다(.env의 LLM_MODE=off). 모델을 켜고 다시 물어 주세요."
        return empty, rec
    register_schema()
    sys_p, user_p = _prompt(q)
    out, st = llm.chat("graph_interpret", sys_p, user_p, options={"num_ctx": 6144})
    rec["stats"] = st
    if out is None:
        err = st.get("error") or st.get("validation_error") or "응답 없음"
        rec["ask"] = f"질문을 해석하지 못했습니다(로컬 모델 {llm.model_name()}: {err[:120]}). Ollama가 켜져 있는지 확인하고 다시 물어 주세요."
        rec["sec"] = round(time.time() - t0, 2)
        return empty, rec
    if True:
        # 모델이 지시문에 따라 뽑은 JSON을 그대로 쓴다. 코드는 '질문에 근거가 없는 값'을 지우거나 형식을 맞출 뿐,
        # 질문에서 낱말을 따로 뽑아 덧붙이거나 바꾸지 않는다(문맥을 모르는 키워드 매칭이 엉뚱한 값을 넣는 것을 막기 위해).
        rec["by"] = "모델"
        d = out.model_dump()
        rec["raw"] = d  # 모델이 낸 JSON 원문(화면 '분석 과정 기록'에 그대로 보여 줌)
        s = {"places": d["places"], "concepts": list(dict.fromkeys(d["concepts"]))[:3],
             "filters": {f["concept"]: f["value"] for f in d["filters"]},
             "period": (d["period"]["start"], d["period"]["end"]) if d["period"] else None,
             "analysis": d["analysis"], "ratio": d["ratio"], "unsupported": d["unsupported"]}
        g = rec["guards"]
        qn = q.replace(" ", "")
        # 1) 기간: 질문에 날짜 표현이 없으면 지운다(지어낸 날짜 방지)
        if s["period"] and not DATE_HINT.search(q):
            g.append(f"질문에 날짜가 없어 기간 {s['period']} 지움")
            s["period"] = None
        # 2) 지명: 질문에 나온 말만 남기고 행정동 이름으로 맞춘다(오타면 되묻기)
        places = []
        for p in s["places"]:
            adm, guess = normalize_place(p)
            # 근거 확인: 그 읍면동의 이름이나 별칭이 질문에 실제로 나와야 한다('제주시 이도2동'처럼 모델이 덧붙인 말은 상관없음)
            if adm and any(a.replace(" ", "") in qn for a in [adm, *_regions()[adm]["aliases"]] if len(a) >= 2):
                places.append(adm)
            elif guess:
                rec["ask"] = f"'{p}'은(는) '{guess}'을(를) 말씀하신 건가요?"
            else:
                g.append(f"지명 '{p}'은(는) 질문에 없거나 읍면동으로 맞출 수 없어 지움")
        s["places"] = list(dict.fromkeys(places))
        # 3) 구분값(업종 등): 값이 질문에 실제로 나온 말이어야 한다
        for dim, val in list(s["filters"].items()):
            if not _word_in(q, str(val)):
                g.append(f"구분값 {dim}='{val}'은(는) 질문에 낱말로 나오지 않아 지움")
                s["filters"].pop(dim)
        # 4) 형식 맞추기: 비율인데 분자·분모가 비었으면 모델이 고른 개념 순서로 채운다
        if s["analysis"] == "ratio" and not s["ratio"] and len(s["concepts"]) >= 2:
            s["ratio"] = {"numerator": s["concepts"][0], "denominator": s["concepts"][1], "scale": 10000}
            g.append("비율의 분자·분모를 모델이 고른 개념 순서로 채움")
        if s["ratio"] and s["analysis"] != "ratio":
            s["ratio"] = None
    if not s["places"] and not rec["ask"]:
        # 지명처럼 보이는 말(○○동·읍·면·리)이 있는데 못 맞췄으면 비슷한 이름을 되묻는다(오타 대비, 값을 채우지는 않음)
        for tok in re.findall(r"[가-힣0-9]{1,6}(?:동|읍|면|리)", q):
            adm, guess = normalize_place(tok)
            if adm:
                rec["ask"] = f"'{tok}' 지역으로 볼까요? (모델 해석에서 지역이 빠졌습니다)"
                break
            if guess:
                rec["ask"] = f"'{tok}'은(는) '{guess}'을(를) 말씀하신 건가요?"
                break
    rec["sec"] = round(time.time() - t0, 2)
    return s, rec
