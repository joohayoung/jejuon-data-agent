"""데이터 접근: 지식 그래프가 고른 허브 자료를 가져온다. 표준 라이브러리만 사용.

- API  : 제주데이터허브 Open API. limit=100(서버 최대), number=1..N을 hasMore=false까지 반복.
         응답은 data/graph/api_cache.sqlite에 저장하고 같은 요청은 다시 부르지 않는다. 자료별 하루 900회에서 멈춘다(허브 쿼터 1,000회).
- 파일 : data/graph/file_cache.sqlite의 ds_<허브ID> 표(원자료 CSV를 한 번 적재한 것). 원자료 CSV를
         data/graph/raw/hub<ID>_*.csv로 넣으면 처음 조회 때 자동으로 적재한다.
- 센터 DB: 운영 환경에서 연결할 자리(인터페이스만).
키: .env의 HUB_PROJECT_KEY(또는 hub_key). 키는 화면·로그·예외 메시지에 남기지 않는다.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "graph"
API_DB = DATA / "api_cache.sqlite"
FILE_DB = DATA / "file_cache.sqlite"
RAW = DATA / "raw"
HUB_URL = "https://open.jejudatahub.net/api/proxy/{key}/{project}"
PAGE = 100
DAILY_CALL_BUDGET = 900
MIN_INTERVAL = 0.3
NUM = re.compile(r"^-?\d+(\.\d+)?$")
_last = 0.0


class DataAccessError(Exception):
    pass


def hub_key() -> str | None:
    for name in ("HUB_PROJECT_KEY", "JEJU_HUB_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(HUB_PROJECT_KEY|hub_key)\s*[=:]\s*[\"']?([A-Za-z0-9_\-]+)", line)
            if m:
                return m.group(2)
    return None


def _mask(text: str) -> str:
    k = hub_key()
    return text.replace(k, "<HUB_KEY>") if k else text


def num(v):
    if isinstance(v, str) and NUM.match(v.strip()):
        return float(v) if "." in v else int(v)
    return v


def _api_db():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(API_DB, timeout=30)
    con.execute("create table if not exists api_cache(dataset integer, params text, fetched text, total integer, rows text, primary key(dataset, params))")
    con.execute("create table if not exists api_calls(day text, n integer, primary key(day))")
    return con


def calls_today(dataset_id: int | None = None) -> int:
    """오늘 호출 수(허브 쿼터는 자료별 하루 1,000회). dataset_id 없으면 가장 많이 쓴 자료 기준."""
    con = _api_db()
    day = dt.date.today().isoformat()
    if dataset_id is None:
        r = con.execute("select max(n) from api_calls where day like ?", (day + "%",)).fetchone()
    else:
        r = con.execute("select n from api_calls where day=?", (f"{day}:{dataset_id}",)).fetchone()
    return (r[0] or 0) if r else 0


def _count_call(con, dataset_id: int):
    key = f"{dt.date.today().isoformat()}:{dataset_id}"
    con.execute("insert into api_calls values(?,1) on conflict(day) do update set n=n+1", (key,))
    con.commit()
    if con.execute("select n from api_calls where day=?", (key,)).fetchone()[0] > DAILY_CALL_BUDGET:
        raise DataAccessError(f"오늘 자료 {dataset_id}의 허브 API 호출이 {DAILY_CALL_BUDGET}회를 넘었습니다(쿼터 보호). 저장된 자료 범위에서만 분석합니다.")


def cached(dataset_id: int, params: dict):
    con = _api_db()
    key = json.dumps(params, ensure_ascii=False, sort_keys=True)
    hit = con.execute("select rows,total,fetched from api_cache where dataset=? and params=?", (dataset_id, key)).fetchone()
    return (json.loads(hit[0]), hit[1], hit[2]) if hit else None


def hub_fetch(dataset_id: int, data_key: str, params: dict, offline: bool = False, max_rows: int = 120000):
    """(행 목록, 전체 건수, 수집 시각). offline=True면 캐시에 없을 때 DataAccessError."""
    global _last
    params = {k.strip(): v for k, v in params.items()}
    hit = cached(dataset_id, params)
    if hit:
        return hit
    if offline:
        raise DataAccessError("저장된 응답이 없습니다(오프라인).")
    key = hub_key()
    if not key:
        raise DataAccessError("허브 키가 없습니다. .env에 HUB_PROJECT_KEY=키 를 넣어 주세요.")
    if not data_key:
        raise DataAccessError(f"자료 {dataset_id}의 API dataKey가 그래프에 없습니다.")
    con = _api_db()
    rows, total, number = [], None, 1
    while True:
        _count_call(con, dataset_id)
        wait = MIN_INTERVAL - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        q = dict(params, limit=PAGE, number=number)
        url = HUB_URL.format(key=data_key, project=key) + "?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "JejuDataAgent/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.load(r)
        except urllib.error.HTTPError as e:
            msg = "허브 프로젝트에 이 자료를 '프로젝트 담기' 했는지 확인해 주세요." if e.code == 403 else ""
            raise DataAccessError(_mask(f"허브 API 오류 {e.code} (자료 {dataset_id}). {msg}")) from None
        except Exception as e:
            raise DataAccessError(_mask(f"허브 API 연결 실패 (자료 {dataset_id}): {type(e).__name__}")) from None
        finally:
            _last = time.time()
        data = body.get("data") or []
        rows += [{k: num(v) for k, v in r.items()} for r in data]
        total = body.get("totCnt", total)
        if not body.get("hasMore") or not data or len(rows) >= max_rows:
            break
        number += 1
    fetched = dt.datetime.now().isoformat(timespec="seconds")
    con.execute("insert or replace into api_cache values(?,?,?,?,?)",
                (dataset_id, json.dumps(params, ensure_ascii=False, sort_keys=True), fetched, total,
                 json.dumps(rows, ensure_ascii=False)))
    con.commit()
    return rows, total, fetched


def date_format(api_params, name: str) -> str:
    for p in api_params or []:
        if p["name"].strip() == name:
            ex = str(p.get("example") or "")
            if re.search(r"YYYYMMDD|^\d{8}$", ex):
                return "%Y%m%d"
            if re.search(r"YYYYMM|^\d{6}$", ex):
                return "%Y%m"
            if re.search(r"YYYY|^\d{4}$", ex):
                return "%Y"
    return "%Y%m%d"


def daterange(start: str, end: str, fmt: str) -> list[str]:
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    out, d = [], s
    while d <= e:
        k = d.strftime(fmt)
        if k not in out:
            out.append(k)
        d += dt.timedelta(days=1)
    return out


# ---------------- 파일 ----------------

def _file_db():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(FILE_DB, timeout=30)
    con.execute("create table if not exists loaded(dataset integer primary key, files text, rows integer, columns text)")
    return con


def _read_csv(path: Path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise DataAccessError(f"{path.name} 인코딩을 읽을 수 없습니다.")
    rd = csv.reader(io.StringIO(text))
    return [h.replace("﻿", "").strip() for h in next(rd)], rd


def local_files(dataset_id: int) -> list[Path]:
    return sorted(RAW.glob(f"hub{dataset_id}_*.csv")) if RAW.exists() else []


def file_loaded(dataset_id: int) -> dict | None:
    r = _file_db().execute("select files,rows,columns from loaded where dataset=?", (dataset_id,)).fetchone()
    return dict(files=json.loads(r[0]), rows=r[1], columns=json.loads(r[2])) if r else None


def has_file(dataset_id: int) -> bool:
    return bool(file_loaded(dataset_id) or local_files(dataset_id))


def file_table(dataset_id: int) -> tuple[str, list[str]]:
    t = f"ds_{dataset_id}"
    files = local_files(dataset_id)
    con = _file_db()
    hit = con.execute("select files,columns from loaded where dataset=?", (dataset_id,)).fetchone()
    if not files:
        if hit:
            return t, json.loads(hit[1])
        raise DataAccessError(f"자료 {dataset_id}의 원자료가 없습니다(허브에서 내려받아 data/graph/raw/hub{dataset_id}_파일명.csv로 저장).")
    sig = json.dumps([f.name + ":" + str(f.stat().st_size) for f in files])
    if hit and hit[0] == sig:
        return t, json.loads(hit[1])
    con.execute(f"drop table if exists {t}")
    cols, n = None, 0
    for f in files:
        header, rd = _read_csv(f)
        if cols is None:
            cols = header
            con.execute(f"create table {t}(" + ",".join(f'"{c}"' for c in cols) + ", _file text)")
        elif header != cols:
            raise DataAccessError(f"{f.name}의 컬럼이 다른 파일과 다릅니다.")
        batch = []
        for row in rd:
            row = (row + [""] * len(cols))[:len(cols)]
            batch.append(row + [f.name])
            if len(batch) >= 20000:
                con.executemany(f"insert into {t} values({','.join('?' * (len(cols) + 1))})", batch)
                n += len(batch)
                batch = []
        con.executemany(f"insert into {t} values({','.join('?' * (len(cols) + 1))})", batch)
        n += len(batch)
    con.execute("insert or replace into loaded values(?,?,?,?)", (dataset_id, sig, n, json.dumps(cols, ensure_ascii=False)))
    con.commit()
    return t, cols


def file_query(dataset_id: int, select: list[str], where: dict | None = None) -> list[dict]:
    """필요한 컬럼만 읽는다(where: {컬럼: [값...]})."""
    t, cols = file_table(dataset_id)
    for c in select + list(where or {}):
        if c not in cols:
            raise DataAccessError(f"자료 {dataset_id}에 컬럼 {c}가 없습니다.")
    sql, args, conds = f"select {','.join(chr(34) + c + chr(34) for c in select)} from {t}", [], []
    for c, vs in (where or {}).items():
        vs = vs if isinstance(vs, (list, tuple)) else [vs]
        conds.append(f'trim("{c}") in ({",".join("?" * len(vs))})')
        args += [str(v).strip() for v in vs]
    if conds:
        sql += " where " + " and ".join(conds)
    cur = _file_db().execute(sql, args)
    return [{k: num(v) for k, v in zip(select, r)} for r in cur]


def file_values(dataset_id: int, column: str, like: str | None = None, top: int = 30) -> list[str]:
    t, cols = file_table(dataset_id)
    if column not in cols:
        return []
    con = _file_db()
    if like:
        cur = con.execute(f'select trim("{column}"), count(*) n from {t} where "{column}" like ? group by 1 order by n desc limit {top}', (f"%{like}%",))
    else:
        cur = con.execute(f'select trim("{column}"), count(*) n from {t} group by 1 order by n desc limit {top}')
    return [r[0] for r in cur]


def center_fetch(dataset_id, where=None, period=None):
    raise DataAccessError("제주빅데이터센터 DB 연결은 센터 운영 환경에서 활성화됩니다(center_db 어댑터).")
