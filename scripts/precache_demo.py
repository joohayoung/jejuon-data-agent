"""시연 질문을 미리 한 번 돌려 허브 API 응답을 캐시에 받아 둔다(이후 시연은 저장된 자료로 바로 답함).

실행: python scripts/precache_demo.py
- 자료별 하루 900회 상한 안에서 받는다. 다 받지 못하면 다음 날 같은 명령으로 이어서 받는다(받은 것은 다시 부르지 않음).
- 질문 해석은 로컬 모델(Ollama)로 한다. Ollama를 켜 두고 실행한다.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from graph import access as da
from graph import pipeline as pp
from graph.interpret import interpret

QUESTIONS = sys.argv[1:] or [
    "애월에 카페가 너무 많을까요? 한림보다 경쟁이 심한지 궁금해요.",
    "한림읍 편의점은 몇 개야?",
    "2026년 8월 노형동과 연동의 방문객 비교해줘",
    "성산에 게스트하우스 많아?",
    "애월 방문객이 요즘 늘고 있어?",
]

if not da.hub_key():
    print("허브 키가 없습니다. .env에 HUB_PROJECT_KEY=키 (또는 hub_key=키)를 넣어 주세요.")
    sys.exit(1)
for q in QUESTIONS:
    t = time.time()
    slots, rec = interpret(q)
    if rec.get("ask"):
        print(f"\n[해석 안 됨] {q}: {rec['ask']}")
        continue
    res = pp.run(q, slots, offline=False)
    print(f"\n[{time.time() - t:.0f}s] {q}")
    for r, m in zip(res.rows, res.metrics):
        state = "전체 43곳" if (not m.reason and m.complete) else ("일부 지역만" if not m.reason else f"보류: {m.reason}")
        print(f"  - {m.name}: {state}")
print("\n오늘 자료별 호출 수:")
con = da._api_db()
for day, n in con.execute("select day, n from api_calls where day like ? order by day", (time.strftime('%Y-%m-%d') + '%',)):
    print(f"  {day.split(':')[-1]}: {n}회")
