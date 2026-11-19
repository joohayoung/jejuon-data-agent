"""jeju-agent의 지식 그래프(kg.sqlite)에서 '데이터 지도'에 필요한 부분만 뽑아 data/data_map.json으로 저장한다.
실행 시점에만 kg.sqlite가 필요하고, 화면(app.py)은 만들어진 json만 읽는다. 표준 라이브러리만 사용.

  python scripts/build_data_map.py 경로/kg.sqlite
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "data_map.json"
ADMIN_GRAINS = [f"grain:space:{x}" for x in ("읍면동", "법정동", "시군구", "시도", "격자")]
# 이 서비스(B)가 실제로 쓰는 허브 자료(tools/provenance.py 기준). 이 자료들끼리의 결합 관계만 담는다.
B_HUB_IDS = [583, 589, 746, 793, 1048, 495, 780, 563, 567, 569, 576, 837, 830, 502, 613, 612, 755, 587, 585, 579]


def short_title(t: str) -> str:
    return re.sub(r"^(제주특별자치도|제주도)[ _]*", "", t).replace("_", " ").strip() or t


def main(kg_path: str) -> None:
    con = sqlite3.connect(kg_path)
    n = {i: dict(type=t, **json.loads(p)) for i, t, p in con.execute("select id,type,props from nodes")}
    out = defaultdict(list)
    for a, b, t, p in con.execute("select src,dst,type,props from edges where type in "
                                  "('BELONGS_TO','ABOUT','HAS_COLUMN','KEYED_BY','JOINABLE')"):
        out[a].append((b, t, json.loads(p)))

    names, ds = {}, {}
    for did, d in n.items():
        if d["type"] != "Dataset":
            continue
        cat = next((b for b, t, _ in out[did] if t == "BELONGS_TO"), None)
        about = [b for b, t, _ in out[did] if t == "ABOUT"]
        grains = {k for c, t, _ in out[did] if t == "HAS_COLUMN" for k, t2, _ in out[c] if t2 == "KEYED_BY"}
        grain = next((g for g in ADMIN_GRAINS if g in grains), None)
        joins = sum(1 for _, t, _ in out[did] if t == "JOINABLE")
        for x in [cat, grain, *about]:
            if x and x not in names:
                names[x] = n.get(x, {}).get("name") or x.rsplit(":", 1)[1]
        end = d.get("auto_update_verified_end") or d.get("period_end") or "?"
        ds[did] = dict(
            l=short_title(d["title"]), t=d["title"], h=d["hub_id"], c=cat, a=d.get("access"),
            p=f"{d.get('period_start') or '?'} ~ {end}",
            d=(d.get("description_gpt") or d.get("description") or "")[:260],
            tp=(d.get("topics") or [])[:5], k=about, g=grain,
            s=round(3 * bool(d.get("verified")) + bool(d.get("auto_update")) + ("API" in str(d.get("access")))
                    + min(joins, 60) / 60, 3),
        )

    order = sorted(ds, key=lambda x: -ds[x]["s"])
    cats = sorted({ds[x]["c"] for x in ds if ds[x]["c"]})
    initial = [next(x for x in order if ds[x]["c"] == c) for c in cats]
    initial += [x for x in order if x not in initial][: max(0, 20 - len(initial))]

    b_ids = {f"ds:{h}" for h in B_HUB_IDS if f"ds:{h}" in ds}
    joins = {}
    for a in b_ids:
        for b, t, p in out[a]:
            if t == "JOINABLE" and b in b_ids and a < b:
                ov = (p.get("overlap") or ["?"])[0][:7]
                joins[f"{a}|{b}"] = f"결합 {p.get('space_key')} · {ov}~"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(total=len(ds), ds=ds, names=names, initial=initial, joins=joins),
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT} 저장: 자료 {len(ds)} · 이름 {len(names)} · 첫 화면 {len(initial)} · 결합 {len(joins)} · "
          f"{OUT.stat().st_size / 1024:.0f}KB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "kg.sqlite"))
