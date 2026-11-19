# 모델 해석 평가 (2026-11-19 16:23, interpret_cases.jsonl, 모델 qwen3:4b, 44문항, 재점검 끔)

| 항목 | 정확도 | 목표 |
|---|---|---|
| 지명 | 100% | 90% |
| 개념 | 98% | 90% |
| 구분값 | 98% | - |
| 분석 | 100% | - |
| 전체 | 95% | 85% |
| 응답 시간 | 중앙값 3.5초 · 최대 16.6초 | - |

## 유형별

| 유형 | 문항 | 전체 정확도 |
|---|---|---|
| 개수 | 6 | 100% |
| 밀도 | 6 | 100% |
| 비교 | 6 | 100% |
| 추이 | 5 | 100% |
| 순위 | 5 | 100% |
| 생활시설 | 6 | 83% |
| 불가 | 4 | 75% |
| 잡담 | 2 | 100% |
| 모호 | 2 | 100% |
| 오타 | 2 | 100% |

## 틀린 문항

- **오라동 근처 병원 몇 개야?** (생활시설) — 틀림: 구분값
  - 기대: places=['오라동'] concepts=[['의료기관수']] filters={} analysis=['count', 'lookup']
  - 모델 1차: {"places": ["오라동"], "concepts": ["의료기관수"], "filters": [{"concept": "업종", "value": "병원"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['오라동'] concepts=['의료기관수'] filters={'업종': '병원'} analysis=count unsupported='' ask=None
- **연동 땅값 앞으로 오를까?** (불가) — 틀림: 개념
  - 기대: places=['연동'] concepts=[] filters={} analysis=['trend', 'lookup'] (unsupported)
  - 모델 1차: {"places": ["연동"], "concepts": ["부동산가격"], "filters": [{"concept": "업종", "value": ""}], "period": null, "analysis": "trend", "ratio": null, "goal": [{"concept": "부동산가격", "want": "high"}], "unsupported": ""}
  - 사용: places=['연동'] concepts=['부동산가격'] filters={} analysis=trend unsupported='' ask=None
