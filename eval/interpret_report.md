# 모델 해석 평가 (2026-11-19 16:01, 모델 qwen3:4b, 44문항, 재점검 켬)

| 항목 | 정확도 | 목표 |
|---|---|---|
| 지명 | 100% | 90% |
| 개념 | 95% | 90% |
| 구분값 | 84% | - |
| 분석 | 95% | - |
| 전체 | 75% | 85% |
| 응답 시간 | 중앙값 9.1초 · 최대 15.9초 | - |
| 재점검이 고친 문항 | 2개 | - |

## 유형별

| 유형 | 문항 | 전체 정확도 |
|---|---|---|
| 개수 | 6 | 67% |
| 밀도 | 6 | 83% |
| 비교 | 6 | 67% |
| 추이 | 5 | 100% |
| 순위 | 5 | 100% |
| 생활시설 | 6 | 50% |
| 불가 | 4 | 50% |
| 잡담 | 2 | 50% |
| 모호 | 2 | 100% |
| 오타 | 2 | 100% |

## 틀린 문항

- **성산에 게스트하우스 많아?** (개수) — 틀림: 구분값
  - 기대: places=['성산읍'] concepts=[['점포수', '숙박시설수']] filters={} analysis=['count', 'lookup', 'ratio']
  - 모델 1차: {"places": ["성산"], "concepts": ["점포수"], "filters": [{"concept": "업종", "value": "게스트하우스"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["성산"], "concepts": ["점포수"], "filters": [{"concept": "업종", "value": "게스트하우스"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['성산읍'] concepts=['점포수'] filters={'업종': '게스트하우스'} analysis=count unsupported='' ask=None
- **표선면 약국 개수 알려줘** (개수) — 틀림: 구분값
  - 기대: places=['표선면'] concepts=[['의료기관수', '점포수']] filters={} analysis=['count', 'lookup']
  - 모델 1차: {"places": ["표선면"], "concepts": ["의료기관수"], "filters": [{"concept": "업종", "value": "약국"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["표선면"], "concepts": ["의료기관수"], "filters": [{"concept": "업종", "value": "약국"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['표선면'] concepts=['의료기관수'] filters={'업종': '약국'} analysis=count unsupported='' ask=None
- **노형동 미용실 포화 상태야?** (밀도) — 틀림: 분석
  - 기대: places=['노형동'] concepts=[['점포수']] filters={'업종': '미용실'} analysis=['ratio']
  - 모델 1차: {"places": ["노형동"], "concepts": ["점포수"], "filters": [{"concept": "업종", "value": "미용실"}], "period": null, "analysis": "lookup", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["노형동"], "concepts": ["점포수"], "filters": [{"concept": "업종", "value": "미용실"}], "period": null, "analysis": "lookup", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['노형동'] concepts=['점포수'] filters={'업종': '미용실'} analysis=lookup unsupported='' ask=None
- **2026년 8월 노형동과 연동의 방문객 비교해줘** (비교) — 틀림: 구분값
  - 기대: places=['노형동', '연동'] concepts=[['방문인구']] filters={} analysis=['compare']
  - 모델 1차: {"places": ["노형동", "연동"], "concepts": ["방문인구"], "filters": [], "period": {"start": "2026-08-01", "end": "2026-08-31"}, "analysis": "compare", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["노형동", "연동"], "concepts": ["방문인구"], "filters": [{"concept": "업종", "value": "방문객"}], "period": {"start": "2026-08-01", "end": "2026-08-31"}, "analysis": "compare", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['노형동', '연동'] concepts=['방문인구'] filters={'업종': '방문객'} analysis=compare unsupported='' ask=None
- **남원읍과 표선면 외국인 방문 비교** (비교) — 틀림: 구분값
  - 기대: places=['남원읍', '표선면'] concepts=[['외국인방문인구']] filters={} analysis=['compare']
  - 모델 1차: {"places": ["남원읍", "표선면"], "concepts": ["외국인방문인구"], "filters": [{"concept": "업종", "value": "외국인"}], "period": null, "analysis": "compare", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["남원읍", "표선면"], "concepts": ["외국인방문인구"], "filters": [{"concept": "업종", "value": "외국인"}], "period": null, "analysis": "compare", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['남원읍', '표선면'] concepts=['외국인방문인구'] filters={'업종': '외국인'} analysis=compare unsupported='' ask=None
- **연동 주차장 부족해?** (생활시설) — 틀림: 구분값
  - 기대: places=['연동'] concepts=[['주차면수']] filters={} analysis=['lookup', 'count', 'ratio']
  - 모델 1차: {"places": ["연동"], "concepts": ["주차면수"], "filters": [{"concept": "시설유형", "value": "주차장"}], "period": null, "analysis": "lookup", "ratio": null, "goal": [{"concept": "주차면수", "want": "low"}], "unsupported": ""}
  - 모델 재점검: {"places": ["연동"], "concepts": ["주차면수"], "filters": [{"concept": "시설유형", "value": "주차장"}], "period": null, "analysis": "lookup", "ratio": null, "goal": [{"concept": "주차면수", "want": "low"}], "unsupported": ""}
  - 사용: places=['연동'] concepts=['주차면수'] filters={'시설유형': '주차장'} analysis=lookup unsupported='' ask=None
- **오라동 근처 병원 몇 개야?** (생활시설) — 틀림: 구분값
  - 기대: places=['오라동'] concepts=[['의료기관수']] filters={} analysis=['count', 'lookup']
  - 모델 1차: {"places": ["오라동"], "concepts": ["의료기관수"], "filters": [{"concept": "업종", "value": "병원"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["오라동"], "concepts": ["의료기관수"], "filters": [{"concept": "업종", "value": "병원"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['오라동'] concepts=['의료기관수'] filters={'업종': '병원'} analysis=count unsupported='' ask=None
- **서귀포 천지동 버스 정류장 몇 개야?** (생활시설) — 틀림: 구분값
  - 기대: places=['천지동'] concepts=[['정류소수']] filters={} analysis=['count', 'lookup']
  - 모델 1차: {"places": ["서귀포", "천지동"], "concepts": ["정류소수"], "filters": [{"concept": "업종", "value": "버스"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["서귀포", "천지동"], "concepts": ["정류소수"], "filters": [{"concept": "업종", "value": "버스"}], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['천지동'] concepts=['정류소수'] filters={'업종': '버스'} analysis=count unsupported='' ask=None
- **한림에 편의점 차리면 순이익 얼마야?** (불가) — 틀림: 개념
  - 기대: places=['한림읍'] concepts=[] filters={'업종': '편의점'} analysis=['lookup', 'sum', 'mean', 'ratio'] (unsupported)
  - 모델 1차: {"places": ["한림"], "concepts": ["점포수"], "filters": [{"concept": "업종", "value": "편의점"}], "period": null, "analysis": "lookup", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["한림"], "concepts": ["점포수"], "filters": [{"concept": "업종", "value": "편의점"}], "period": null, "analysis": "lookup", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['한림읍'] concepts=['점포수'] filters={'업종': '편의점'} analysis=lookup unsupported='' ask=None
- **연동 땅값 앞으로 오를까?** (불가) — 틀림: 개념
  - 기대: places=['연동'] concepts=[] filters={} analysis=['trend', 'lookup'] (unsupported)
  - 모델 1차: {"places": ["연동"], "concepts": ["부동산가격"], "filters": [], "period": null, "analysis": "trend", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": ["연동"], "concepts": ["부동산가격"], "filters": [], "period": null, "analysis": "trend", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=['연동'] concepts=['부동산가격'] filters={} analysis=trend unsupported='' ask=None
- **안녕** (잡담) — 틀림: 분석
  - 기대: places=[] concepts=[] filters={} analysis=['lookup']
  - 모델 1차: {"places": [], "concepts": [], "filters": [], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 모델 재점검: {"places": [], "concepts": [], "filters": [], "period": null, "analysis": "count", "ratio": null, "goal": [], "unsupported": ""}
  - 사용: places=[] concepts=[] filters={} analysis=count unsupported='' ask=None
