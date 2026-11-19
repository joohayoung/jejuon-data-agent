"""반출 사전 점검 (지시서 §6). 결과물마다 데이터군·집계 유형·10 미만 여부·처리·판정과 이유를 낸다.

결과물(artifact) 기술 방식(dict):
  file          결과물 파일 경로(프로젝트 기준)
  kind          table | chart | text | code | raw | form
  format        png | jpg | html | md | csv | txt | xlsx | json | py ...
  agg_type      simple(단순집계) | applied(응용집계) | visual(시각화) | raw(원본·발췌) | code
  datasets      사용 데이터 코드명 목록(policy datasets 키)
  simple_values 결과물에 보이는 단순집계 수치(10 미만 검사용)
  fields        결과물에 보이는 필드 이름(상호명·주소 검사용)
  source_text   출처 표기
  reason        활용 사유
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ORDER = {"가능": 0, "조건부": 1, "불가": 2}
TEXT_FORMATS = {"csv", "txt", "tsv", "xlsx", "xls", "json"}


@lru_cache(maxsize=None)
def rules() -> dict:
    return yaml.safe_load((ROOT / "policy" / "export_rules.yaml").read_text(encoding="utf-8"))


def small_value_label(v, threshold: float | None = None, label: str | None = None):
    """단순집계 값 하나에 범주 처리를 적용한다. 10 미만이면 '10 미만', 아니면 그대로."""
    r = rules()
    threshold = r["small_value_threshold"] if threshold is None else threshold
    label = r["small_value_label"] if label is None else label
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return v
    return label if v < threshold else v


def scan_code(paths: list[Path]) -> list[dict]:
    """소스코드·노트북에서 데이터 샘플 출력 패턴을 찾는다."""
    pats = [re.compile(p) for p in rules()["common"]["code_sample_patterns"]]
    hits = []
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if str(p).endswith(".ipynb"):
            try:
                text = "\n".join("".join(c.get("source", [])) for c in json.loads(text).get("cells", []))
            except json.JSONDecodeError:
                pass
        for i, line in enumerate(text.splitlines(), 1):
            for pat in pats:
                if pat.search(line):
                    hits.append({"file": str(p), "line": i, "pattern": pat.pattern})
    return hits


def project_code_files() -> list[Path]:
    skip = {".venv", "data", "outputs", "metrics", "ref", "__pycache__", ".git"}
    return [p for p in ROOT.rglob("*") if p.suffix in (".py", ".ipynb")
            and not any(part in skip for part in p.relative_to(ROOT).parts)]


def check_artifact(a: dict) -> dict:
    R = rules()
    groups = {R["datasets"][d]["group"] for d in a.get("datasets", [])}
    restricted = "restricted" in groups
    fmt = (a.get("format") or Path(a["file"]).suffix.lstrip(".")).lower()
    verdict, reasons, treatment = "가능", [], []

    def worse(v, why):
        nonlocal verdict
        if ORDER[v] > ORDER[verdict]:
            verdict = v
        reasons.append(f"[{v}] {why}")

    # 상가 정보 상호명·주소·좌표: 항상 불가
    forbidden = {f for d in a.get("datasets", []) for f in R["datasets"][d].get("always_forbidden_fields", [])}
    shown = forbidden & set(a.get("fields", []))
    if shown:
        worse("불가", f"상가 정보 {', '.join(sorted(shown))} 출력")

    agg = a.get("agg_type")
    small = [v for v in a.get("simple_values", []) if isinstance(v, (int, float)) and not math.isnan(v)
             and v < R["small_value_threshold"]]

    if agg == "code":
        hits = scan_code([ROOT / a["file"]] if not Path(a["file"]).is_absolute() else [Path(a["file"])])
        if hits:
            worse("불가", f"데이터 샘플 출력 코드 {len(hits)}곳(예: {hits[0]['pattern']} {hits[0]['line']}행)")
        else:
            reasons.append("[가능] 데이터 샘플 출력 코드 없음")
    elif agg == "raw":
        if restricted:
            worse("불가", "제한 데이터군 원본·발췌")
        else:
            reasons.append("[가능] 개방 데이터군 원본")
    elif agg == "form":
        reasons.append("[가능] 신청서 양식(데이터 수치 없음)")
    else:
        if restricted and fmt in TEXT_FORMATS:
            worse("불가", f"제한 데이터군 텍스트·스프레드시트 형식({fmt})")
        if restricted and agg in ("visual", "simple", "applied") and fmt in ("html", "svg"):
            worse("조건부", f"{fmt.upper()} 형식은 반출 형식이 아님 → png·jpg 그림으로 캡처해 반출")
            treatment.append("png 캡처")
        if restricted and agg == "visual" and fmt not in R["groups"]["restricted"]["allowed_image_formats"] + ["html", "svg"]:
            worse("불가", f"시각화는 png·jpg만 허용({fmt})")
        # 단순집계 수치가 보이면(응용집계 표 안에 섞여 있어도) 10 미만을 검사한다
        if small:
            treatment.append(f"범주 처리('{R['small_value_label']}')")
            if restricted:
                worse("조건부", f"단순집계 10 미만 값 {len(small)}개")
            else:
                reasons.append(f"[가능] 개방 데이터군이나 표시 규칙(지시서 §6-1)상 10 미만 {len(small)}개 범주 처리")
        elif a.get("simple_values"):
            reasons.append(f"[가능] 단순집계 수치 {len(a['simple_values'])}개, 10 미만 없음")
        if agg == "applied":
            reasons.append("[가능] 응용집계(비율·증감률·순위)")
        elif agg == "visual" and fmt in R["groups"]["restricted"]["allowed_image_formats"]:
            reasons.append(f"[가능] 시각화 {fmt}")
        if not restricted:
            reasons.append("[가능] 개방 데이터군")

    if R["common"]["require_source_and_reason"] and agg not in ("code", "form"):
        missing = [k for k, n in (("source_text", "출처"), ("reason", "활용 사유")) if not a.get(k)]
        if missing:
            worse("조건부", f"{'·'.join({'source_text': '출처', 'reason': '활용 사유'}[m] for m in missing)} 기재 필요(빠지면 재요청·반려)")

    return {
        "file": a["file"], "kind": a.get("kind"), "format": fmt,
        "데이터군": sorted(R["groups"][g]["label"] for g in groups) or ["해당 없음"],
        "집계 유형": {"simple": "단순집계", "applied": "응용집계", "visual": "시각화", "raw": "원본·발췌",
                   "code": "소스코드", "form": "양식"}.get(agg, agg),
        "10 미만 값": len(small), "적용 처리": treatment or ["없음"], "판정": verdict, "이유": reasons,
        "datasets": a.get("datasets", []), "출처": a.get("source_text"), "활용 사유": a.get("reason"),
        "참고": R["groups"]["restricted"]["commercial_note"] if restricted else
        (R["groups"]["open"]["commercial_note"] if groups else None),
    }


def run(artifacts: list[dict], out: Path | None = None, include_code_scan: bool = True) -> dict:
    R = rules()
    results = [check_artifact(a) for a in artifacts]
    report = {
        "label": R["display_label"],
        "rules_source": R["source"],
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "results": results,
    }
    if include_code_scan:
        hits = scan_code(project_code_files())
        report["code_scan"] = {"files": len(project_code_files()), "sample_output_hits": hits,
                               "판정": "불가" if hits else "가능"}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return report
