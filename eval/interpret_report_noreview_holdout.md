# 모델 해석 평가 (2026-11-19 16:24, interpret_holdout.jsonl, 모델 qwen3:4b, 15문항, 재점검 끔)

| 항목 | 정확도 | 목표 |
|---|---|---|
| 지명 | 100% | 90% |
| 개념 | 93% | 90% |
| 구분값 | 100% | - |
| 분석 | 93% | - |
| 전체 | 87% | 85% |
| 응답 시간 | 중앙값 3.6초 · 최대 6.4초 | - |

## 유형별

| 유형 | 문항 | 전체 정확도 |
|---|---|---|
| 개수 | 2 | 100% |
| 밀도 | 2 | 50% |
| 비교 | 2 | 100% |
| 추이 | 2 | 100% |
| 순위 | 2 | 100% |
| 생활시설 | 2 | 100% |
| 불가 | 1 | 0% |
| 잡담 | 1 | 100% |
| 모호 | 1 | 100% |

## 틀린 문항

- **한경면 편의점 너무 많은 거 아냐?** (밀도) — 틀림: 분석
  - 기대: places=['한경면'] concepts=[['점포수']] filters={'업종': '편의점'} analysis=['ratio']
  - 모델 1차: {"places": ["한경면"], "concepts": ["점포수"], "filters": [{"concept": "업종", "value": "편의점"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['한경면'] concepts=['점포수'] filters={'업종': '편의점'} analysis=count unsupported='' ask=None
- **내년 여름에 함덕 관광객 몇 명 올지 알려줘** (불가) — 틀림: 개념
  - 기대: places=['조천읍'] concepts=[] filters={} analysis=['trend', 'lookup'] (unsupported)
  - 모델 1차: {"places": ["함덕"], "concepts": ["방문인구"], "filters": [], "period": null, "analysis": "lookup", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['조천읍'] concepts=['방문인구'] filters={} analysis=lookup unsupported='' ask=None
