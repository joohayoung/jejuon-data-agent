"""로컬 모델(Ollama) 질문 해석 점검. 질문마다 모델 해석·코드 가드 결과·걸린 시간을 보여 준다.

실행: python scripts/check_interpret.py
      python scripts/check_interpret.py "성산에 게스트하우스 많아?"
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from agent import llm
from graph.interpret import interpret

QUESTIONS = sys.argv[1:] or [
    "애월에 카페가 너무 많을까요? 한림보다 경쟁이 심한지 궁금해요.",
    "한림읍 편의점은 몇 개야?",
    "2026년 8월 노형동과 연동의 방문객 비교해줘",
    "성산에 게스트하우스 많아?",
    "애월 방문객이 요즘 늘고 있어?",
    "내일 애월에 사람이 얼마나 몰릴지 예측해줘",
    "노현동 유동인구 알려줘",
]

print(f"모델: {llm.model_name()} / LLM_MODE={llm.llm_mode()}")
for q in QUESTIONS:
    t = time.time()
    s, rec = interpret(q)
    calls = rec.get("stats", {}).get("calls", [])
    tok = f"{calls[-1].get('prompt_eval_count')}/{calls[-1].get('eval_count')}" if calls else "-"
    print(f"\n[{time.time() - t:.1f}s · {rec['by']} · 토큰 {tok}] {q}")
    print("  모델 원문:", rec.get("raw"))
    print("  사용:", s)
    if rec["guards"]:
        print("  가드:", " / ".join(rec["guards"]))
    if rec.get("ask"):
        print("  되묻기:", rec["ask"])
    if rec.get("stats", {}).get("error"):
        print("  모델 오류:", rec["stats"]["error"])
