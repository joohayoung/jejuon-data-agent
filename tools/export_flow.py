"""반출 신청·점검 흐름: 도민 신청 → 운영자 점검(데이터별 동의/제외+사유) → 도민이 승인된 원문 데이터를 확인.
(팀원 jeju-analyst-poc의 tools/export_flow.py를 가져옴. 분석 세션용 create()는 이 앱에서 쓰지 않아 뺐다.)

신청 기록은 SQLite(data/app.db, git 제외)의 requests 테이블에 둔다. 상호명·주소·좌표·개인 정보는 담지 않는다.
점검은 `UPDATE … WHERE status='대기'`로 한 번만 반영되어, 운영자 둘이 동시에 눌러도 먼저 저장된 점검이 남는다.
상태: 대기 → 승인(전부 동의) / 부분승인(일부 제외) / 반려(모두 제외).
정책상 '불가'로 나온 결과물은 운영자가 동의할 수 없고, 자동으로 제외된다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import sqlite3
from pathlib import Path

from tools.export_check import rules

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "app.db"
DEFAULT_REASON = "보안상 반출을 제한합니다."
POLICY_REASON = "반출 정책상 반출 불가로 판정되어 제외했습니다."
STATUSES = ("대기", "승인", "부분승인", "반려")


def _con() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    con.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
                "status TEXT NOT NULL, rec TEXT NOT NULL)")
    return con


def _check_id(rid: str) -> str:
    if not rid.replace("-", "").isalnum():  # 형식 점검(쿼리는 매개변수로 넘기므로 주입은 없음)
        raise ValueError("신청 번호 형식이 올바르지 않습니다")
    return rid


def admin_code() -> str:
    """운영자 화면 접근 코드(.env ADMIN_CODE). 없으면 빈 문자열(PoC 시연용: 코드 없이 열림)."""
    if "ADMIN_CODE" in os.environ:
        return os.environ["ADMIN_CODE"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("ADMIN_CODE="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def create_raw(kind: str, question: str, purpose: str, items: list[dict], datasets: list[dict], note: str = "",
               area: str | None = None, industry: str | None = None, doc: dict | None = None) -> dict:
    """항목이 이미 만들어진 신청을 저장한다(데이터 단위 신청 등). kind: 'result'(분석 결과물) / 'data'(데이터)."""
    rid = f"REQ-{dt.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    rec = {"id": rid, "kind": kind, "created_at": dt.datetime.now().isoformat(timespec="seconds"), "status": "대기",
           "question": question, "followups": [], "area": area, "industry": industry, "menu": "데이터 반출" if kind == "data" else None,
           "purpose": purpose, "datasets": datasets, "items": items, "doc": doc, "label": rules()["display_label"],
           "decided_at": None, "admin_note": note}
    save(rec)
    return rec


def save(rec: dict) -> None:
    with _con() as con:
        con.execute("INSERT OR REPLACE INTO requests (id, created_at, status, rec) VALUES (?,?,?,?)",
                    (rec["id"], rec["created_at"], rec["status"], json.dumps(rec, ensure_ascii=False)))


def load(rid: str) -> dict | None:
    with _con() as con:
        row = con.execute("SELECT rec FROM requests WHERE id=?", (_check_id(rid.strip()),)).fetchone()
    return json.loads(row[0]) if row else None


def list_all() -> list[dict]:
    with _con() as con:
        rows = con.execute("SELECT rec FROM requests ORDER BY created_at DESC").fetchall()
    return [json.loads(r[0]) for r in rows]


def decide(rid: str, choices: dict[str, dict], admin_note: str = "") -> dict:
    """choices: {파일: {"approve": bool, "reason": str}}. 불가 항목은 동의할 수 없다.
    제외하면 사유를 적는다(비어 있으면 기본 사유 '보안상…'). 점검은 한 번만 반영된다."""
    rec = load(rid)
    if rec is None:
        raise KeyError(rid)
    if rec["status"] != "대기":
        raise ValueError("이미 점검이 끝난 신청입니다")
    for it in rec["items"]:
        c = choices.get(it["file"], {})
        if it["locked"]:
            continue
        if c.get("approve"):
            it["decision"], it["exclude_reason"] = "동의", ""
        else:
            it["decision"], it["exclude_reason"] = "제외", (c.get("reason") or "").strip() or DEFAULT_REASON
    ok = sum(it["decision"] == "동의" for it in rec["items"])
    rec["status"] = "승인" if ok == len(rec["items"]) else ("반려" if ok == 0 else "부분승인")
    rec["admin_note"] = admin_note.strip()
    rec["decided_at"] = dt.datetime.now().isoformat(timespec="seconds")
    with _con() as con:  # 아직 '대기'일 때만 반영 → 동시에 눌러도 먼저 저장된 점검이 남는다
        cur = con.execute("UPDATE requests SET status=?, rec=? WHERE id=? AND status='대기'",
                          (rec["status"], json.dumps(rec, ensure_ascii=False), rec["id"]))
    if cur.rowcount != 1:
        raise ValueError("이미 점검이 끝난 신청입니다")
    return rec


def approved_files(rec: dict) -> list[dict]:
    """도민이 내려받을 수 있는 것: 점검이 끝났고 동의된 결과물만."""
    if rec["status"] not in ("승인", "부분승인"):
        return []
    return [it for it in rec["items"] if it["decision"] == "동의"]


# ---------------- 운영 현황(운영자 화면): 답하지 못한 질문 기록 ----------------
UNANSWERED = ROOT / "data" / "unanswered.jsonl"


def log_unanswered(question: str, reason: str, slots: dict | None = None) -> None:
    """자료가 없거나 답할 수 없는 요구라 보류한 질문을 남긴다(운영자가 어떤 자료가 더 필요한지 보는 용도, git 제외)."""
    UNANSWERED.parent.mkdir(parents=True, exist_ok=True)
    row = {"일시": dt.datetime.now().isoformat(timespec="seconds"), "질문": question, "사유": reason,
           "해석": {k: (slots or {}).get(k) for k in ("places", "concepts", "filters", "analysis", "unsupported")}}
    with UNANSWERED.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def unanswered() -> list[dict]:
    if not UNANSWERED.exists():
        return []
    return [json.loads(x) for x in UNANSWERED.read_text(encoding="utf-8").splitlines() if x.strip()][::-1]
