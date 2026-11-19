"""허브 원문 데이터 반출 신청 (서비스 흐름 5~9번).

팀원 jeju-analyst-poc의 tools/data_export.py를 이 앱에 맞춰 옮겼다.
 - 신청 대상 목록: 지식 그래프(data/graph/kg.sqlite)의 제주데이터허브 자료 1,259종. 답변에 쓴 자료는 미리 골라 둔다.
 - 사전 점검: 같은 반출 규칙(policy/export_rules.yaml, tools/export_check.py).
   제한 데이터군(카드·유동인구·외식업 POS 등): 원본·발췌 불가, 그림(png·jpg)·응용집계 가능, 단순집계 조건부,
   집계·시각화의 csv·xlsx는 원칙적 불가지만 조건부(예외 사유 필요, 운영자 판단, 2026-11-18 결정)
   개방 데이터군: 모두 가능
 - 신청·점검 기록: tools/export_flow.py (data/app.db)
 - 반출 대상은 분석 결과 그림·표가 아니라 허브 원문 데이터다. 승인되면 deliver()가 원문을 넘기는 방법을 돌려준다.
   지금(데모)은 허브 원문 반출 권한이 없어 허브 데이터 페이지 링크로 연결하고, 허브 연동 후에는 deliver() 한 곳만 바꾸면 된다.
"""
from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache

from tools import export_check, export_flow

FORMS = {"원본·발췌": "raw", "단순집계(건수·합계)": "simple", "응용집계(비율·순위·증감률)": "applied", "시각화(그림)": "visual"}
FORMATS = ["png", "jpg", "csv", "xlsx", "html"]
GROUP_LABEL = {"restricted": "제한 데이터군", "open": "개방 데이터군", "external": "외부 데이터(점검 대상 아님)"}
HUB_VIEW_URL = "https://jejudatahub.net/data/view/data/{hub_id}"

# 센터 반출 규칙의 제한 데이터군(제공기관: 비씨카드·SKT·KT·나이스지니데이타·한국기업데이터·탐나는전·데이터웨이)에 해당하는 허브 자료.
# 팀원 코드(LOCAL·data_catalog)에서 제한으로 분류한 허브 번호 + 제공기관·자료 이름으로 판별한다.
RESTRICTED_HUB = {583, 589, 746, 1048, 495, 502, 755, 563, 564, 565, 566, 567, 595}
RESTRICTED_WORDS = re.compile(r"카드|유동인구|POS|외식업|기업|SKT|KT|통신|매출|이용금액|탐나는전|나이스")


@lru_cache(maxsize=1)
def _datasets() -> list[dict]:
    from graph import engine as en
    g = en.kg()
    return sorted((v for v in g.n.values() if v["type"] == "Dataset"), key=lambda d: d["hub_id"])


def group_of(d: dict) -> str:
    if d["hub_id"] in RESTRICTED_HUB:
        return "restricted"
    providers = export_check.rules()["groups"]["restricted"]["providers"]
    hay = f"{d.get('title', '')} {d.get('provider') or ''}"
    if any(p in hay for p in providers) or RESTRICTED_WORDS.search(hay):
        return "restricted"
    return "open"


@lru_cache(maxsize=1)
def options() -> list[dict]:
    """반출 신청 대상: 제주데이터허브 자료 1,259종(지식 그래프 기준)."""
    out = []
    for d in _datasets():
        hid = d["hub_id"]
        out.append({"id": f"hub:{hid}", "label": f"[허브 {hid}] {d['title']} · {d.get('category') or '-'} · {d.get('access') or '-'}"[:150],
                    "group": group_of(d), "name": d["title"], "hub_id": hid, "type": d.get("access"),
                    "period": f"{d.get('period_start') or '?'}~{d.get('period_end') or '현재'}",
                    "available": "hub", "available_note": "허브 원문 반출 대상"})
    return out


def option_ids_for_hub(hub_ids: list[int]) -> set[str]:
    """답변에 쓴 허브 번호 → 신청 목록 id."""
    return {f"hub:{int(h)}" for h in hub_ids}


def precheck(opt: dict, form: str, fmt: str, scope: str = "", reason: str = "", exception: str = "") -> dict:
    """한 건(데이터 × 반출 형태 × 파일 형식)을 반출 규칙으로 사전 점검한다."""
    R = export_check.rules()
    agg = FORMS[form]
    base = {"file": f"data:{opt['id']}:{agg}:{fmt}", "name": f"{opt['name']} · {form} · {fmt}", "kind": "data", "format": fmt,
            "dataset_id": opt["id"], "scope": scope, "period": opt.get("period"), "활용 사유": reason,
            "보유": opt.get("available_note", ""), "보유 여부": opt.get("available", "")}
    if opt["group"] == "external":
        return {**base, "집계 유형": form, "데이터군": [GROUP_LABEL["external"]], "사전 판정": "가능",
                "사전 이유": ["외부 공개 데이터라 센터 반출 점검 대상이 아닙니다(출처와 이용조건만 표시)"], "처리": ["없음"]}
    code = "_pre_" + opt["id"].replace(":", "_")
    R["datasets"].setdefault(code, {"group": opt["group"]})          # 점검 함수가 쓰는 데이터군 표(메모리에만 추가)
    a = {"file": base["file"], "kind": "data", "format": fmt, "agg_type": agg, "datasets": [code], "simple_values": [],
         "fields": [], "source_text": f"{opt['name']}({opt.get('period')})", "reason": reason or "활용 사유 미기재"}
    r = export_check.check_artifact(a)
    verdict, why, treat = r["판정"], [x.split("] ", 1)[-1] for x in r["이유"]], list(r["적용 처리"])
    needs_exc = False
    if opt["group"] == "restricted" and fmt in export_check.TEXT_FORMATS and agg != "raw":
        # 2026-11-18 결정: 제한 데이터군 집계·시각화의 csv·xlsx는 '원칙적 불가'지만 조건부(예외 사유 필요, 운영자 판단). 원본·발췌는 계속 불가.
        needs_exc = True
        verdict = "조건부"
        why = [x for x in why if "텍스트·스프레드시트 형식" not in x]
        why.append("제한 데이터군의 csv·xlsx는 원칙적으로 불가 — 예외 사유를 적으면 운영자가 판단합니다(조건부)")
        treat = ["예외 사유 기재"] + (["범주 처리('10 미만')"] if agg == "simple" else [])
        if not exception.strip():
            why.append("예외 사유(왜 csv·xlsx가 필요한지)가 아직 없습니다")
    if agg == "simple" and opt["group"] == "restricted" and verdict == "가능":
        verdict = "조건부"
        why.append("단순집계는 10 미만 값이 있으면 범주 처리('10 미만')한 뒤 반출")
        treat = ["범주 처리('10 미만')"]
    if not reason:
        verdict = verdict if verdict == "불가" else "조건부"
        why.append("활용 사유를 적어야 반려되지 않습니다")
    return {**base, "집계 유형": form, "데이터군": [GROUP_LABEL[opt["group"]]], "사전 판정": verdict, "사전 이유": why,
            "처리": treat or ["없음"], "예외 필요": needs_exc, "예외 사유": exception.strip()}


def rules_table() -> list[dict]:
    """도민 화면에 보여 줄 '반출 형태별 가능 여부' 안내표(제한·개방 데이터군)."""
    out = []
    for form in FORMS:
        row = {"반출 형태": form}
        for g, label in (("restricted", "제한 데이터군(카드·유동인구 등)"), ("open", "개방 데이터군(버스·와이파이·날씨 등)")):
            fmts = {}
            for fmt in ("png", "csv"):
                opt = {"id": f"_demo_{g}", "name": "예시", "group": g, "period": ""}
                fmts[fmt] = precheck(opt, form, fmt, reason="안내")["사전 판정"]
            row[label] = f"그림(png) {fmts['png']} · csv {fmts['csv']}"
        out.append(row)
    return out


def create(items: list[dict], purpose: str, question: str | None = None, area: str | None = None, note: str = "") -> dict:
    """사전 점검한 항목들로 원문 데이터 반출 신청을 저장한다(대기). question: 도민이 한 질문(운영자가 확인)."""
    if not items:
        raise ValueError("반출할 데이터를 고르지 않았습니다")
    rid_items = []
    for it in items:
        banned = it["사전 판정"] == "불가"
        rid_items.append({**it, "decision": "제외" if banned else None,
                          "exclude_reason": export_flow.POLICY_REASON if banned else "", "locked": banned})
    names = ", ".join(sorted({i["name"].split(" · ")[0] for i in items}))[:150]
    rec = export_flow.create_raw(
        kind="data", question=question or f"[데이터 반출 신청] {len(items)}건 — {names}", area=area,
        purpose=purpose, items=rid_items,
        datasets=[{"data": f"{i['name'].split(' · ')[0]}({i.get('period')})", "group": i["데이터군"][0],
                   "external": i["데이터군"][0].startswith("외부")} for i in items],
        note=note)
    return rec


def approval_statement(rec: dict) -> str:
    """승인 결과 내역서(도민이 받는 문서): 데이터별 승인·제외와 조건."""
    lines = ["# 데이터 반출 승인 내역서", "", f"- 신청 번호: {rec['id']}", f"- 신청 일시: {rec['created_at']}",
             f"- 질문·신청 내용: {rec.get('question')}",
             f"- 점검 결과: {rec['status']} (점검 완료 {rec.get('decided_at') or '-'})", f"- 활용 사유: {rec.get('purpose')}",
             f"- 규칙: {rec.get('label')}", ""]
    if rec.get("admin_note"):
        lines += [f"- 운영자 메모: {rec['admin_note']}", ""]
    lines += ["| 데이터 · 반출 형태 · 형식 | 범위 | 판정 | 조건 | 사유 | 원문 |", "|---|---|---|---|---|---|"]
    for it in rec["items"]:
        d = it["decision"] or "점검 중"
        cond = ", ".join(it.get("처리") or []) if d == "동의" else "-"
        why = it.get("exclude_reason") or (f"예외 사유: {it['예외 사유']}" if it.get("예외 사유") else "")
        hid = hub_id_of(it)
        link = HUB_VIEW_URL.format(hub_id=hid) if (d == "동의" and hid) else "-"
        lines.append(f"| {it['name']} | {it.get('scope') or '-'} | {d} | {cond} | {why} | {link} |")
    lines += ["", "승인된 항목은 제주데이터허브의 해당 데이터 원문으로 연결됩니다. 이 문서는 반출 파일이 아니라 승인 내역입니다.",
              f"출력 일시: {dt.datetime.now():%Y-%m-%d %H:%M}"]
    return "\n".join(lines) + "\n"


# =====================================================================================================
# 승인된 원문 데이터 전달 지점 — 허브 연동은 deliver() 한 곳만 바꾸면 된다
# =====================================================================================================

def hub_id_of(item: dict) -> int | None:
    """신청 항목이 가리키는 제주데이터허브 데이터 번호."""
    did = str(item.get("dataset_id") or "")
    if did.startswith("hub:"):
        try:
            return int(did.split(":")[1])
        except ValueError:
            return None
    return None


def deliver(item: dict) -> dict:
    """승인된 항목의 원문 데이터를 도민에게 넘기는 방법.
    지금(데모): 제주데이터허브의 해당 데이터 상세 페이지 주소를 돌려준다(원문 반출 권한이 없어 링크로만 연결).
    허브 연동 후: 이 함수가 허브 원문 다운로드를 호출해 {"mode": "download", "data": bytes, "name": ..., "mime": ...}를 돌려주도록 바꾸면 된다."""
    hid = hub_id_of(item)
    if hid is None:
        return {"mode": "none", "note": "외부 공개 데이터라 허브 반출 대상이 아닙니다. 출처 사이트에서 직접 이용하세요."}
    return {"mode": "link", "url": HUB_VIEW_URL.format(hub_id=hid), "hub_id": hid,
            "note": f"제주데이터허브 {hid}번 데이터 페이지로 연결됩니다."}


# ---------------- 운영 현황(운영자 화면): 서비스가 쓰는 허브 자료의 신선도 ----------------
SERVICE_HUB = [583, 589, 793, 746, 862, 863, 861, 837]   # 분석 관점·시연 질문에 쓰는 허브 자료(README 6장)


def freshness(today: dt.date | None = None) -> list[dict]:
    """허브 갱신 주기와 실제 최신 기준일의 차이(지식 그래프 기록 기준)."""
    today = today or dt.date.today()
    by = {d["hub_id"]: d for d in _datasets()}
    out = []
    for h in SERVICE_HUB:
        d = by.get(h)
        if not d:
            continue
        end = d.get("auto_update_verified_end") or d.get("period_end")
        months = None
        if end:
            e = dt.date.fromisoformat(str(end)[:10])
            months = (today.year - e.year) * 12 + today.month - e.month
        out.append({"허브 번호": h, "데이터": d["title"], "허브 갱신 주기": d.get("update_cycle") or "-",
                    "최신 기준일": str(end)[:10] if end else "-", "경과(개월)": months,
                    "상태": "-" if months is None else ("최신" if months <= 3 else ("확인 필요" if months < 24 else "갱신 멈춤"))})
    return out
