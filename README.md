# JEJU:ON (제주온) · 제주 데이터 동네상담소

jeju-agent(A)의 **지식 그래프 데이터 선별**과 jeju-analyst-poc(B)의 **화면·판정·로컬 LLM 호출**을 합친 범용 버전입니다.
창업 질문만이 아니라 제주데이터허브 자료로 답할 수 있는 질문이면 같은 방식으로 진단표를 만듭니다.

```
질문 ─▶ ① 해석: 로컬 LLM(qwen3:4b)이 검수 개념 162개 안에서 슬롯 추출 + 코드 가드   graph/interpret.py
     ─▶ ② 렌즈: 질문 지표 + 분석 관점(상권·인구 등)의 관련 지표를 '개념'으로 구성       graph/lenses.yaml
     ─▶ ③ 선별: 지식 그래프가 개념마다 자료·컬럼·지역 키·필터를 고름(허브 1,259종)      graph/engine.py
     ─▶ ④ 검증: 지표 단위 합산 금지, 결합 가능 여부, 기간, 개인정보 컬럼 등             graph/engine.py
     ─▶ ⑤ 계산: 제주 43개 읍면동 전체 → 순위·중앙값·높음/보통/낮음                      graph/pipeline.py
     ─▶ ⑥ 화면: 진단 카드·위치/순위/추이 그래프·쉬운 말 요약·이 답변의 데이터 지도·반출 점검   app.py
```

- **LLM은 ① 해석에만** 씁니다. 자료 선택·계산·판정·문장의 숫자는 모두 코드가 만듭니다.
- 특정 데이터에 묶이지 않습니다. 렌즈의 지표는 '점포수 ÷ 방문인구'처럼 **개념**으로 적고, 실제 자료는 그래프가 고릅니다.
  새 분야를 깊게 보려면 `graph/lenses.yaml`에 렌즈를 추가하면 됩니다.
- 자동 지표에는 유리·불리 같은 가치 판정을 붙이지 않고, 제주 읍면동 사이 상대 위치(높음·보통·낮음)만 보여 줍니다.

## 실행

1. Ollama에 모델 준비(한 번만)

```
ollama pull qwen3:4b
```

2. `.env` (이 폴더) — 허브 키는 `HUB_PROJECT_KEY=` 또는 `hub_key=` 둘 다 읽습니다. 나머지는 선택입니다(`.env.example` 참고).
3. 실행: `run.bat` (처음 실행 때 가상환경과 패키지를 설치합니다) → 브라우저 http://localhost:8501
4. 시연 전 한 번: 시연 질문 5개에 필요한 허브 API 응답을 미리 받아 둠(약 10~20분, 이후 시연은 바로 답함)

```
.venv\Scripts\python scripts\precache_demo.py
```

5. 모델 해석 점검(선택):

```
.venv\Scripts\python scripts\check_interpret.py
```

| 설정(.env) | 뜻 |
|---|---|
| `OLLAMA_MODEL` | 기본 `qwen3:4b`. 폴백으로 `kanana-2.1b` 등 |
| `LLM_MODE` | `on`(기본). 질문 해석은 로컬 모델만 하며, `off`면 해석하지 않고 안내만 표시 |
| `GRAPH_OFFLINE` | `1`이면 허브 API를 부르지 않고 저장된 자료만 사용(시연·시험) |
| `OLLAMA_NUM_GPU`, `OLLAMA_NUM_THREAD` | 센터 PC(VRAM 3GB, 6코어) 흉내 측정용 |

## 데이터

| 위치 | 내용 |
|---|---|
| `data/graph/kg.sqlite` | 지식 그래프(A에서 GPT로 한 번 구축). 운영 중에는 조회만 |
| `data/graph/api_cache.sqlite` | 허브 API 응답 캐시(같은 요청은 다시 부르지 않음, 하루 900회 상한) |
| `data/graph/file_cache.sqlite` | 파일 자료 적재본(현재 793 상가, 746 카드). 다른 파일 자료는 허브에서 내려받아 `data/graph/raw/hub<번호>_이름.csv`로 넣으면 처음 조회 때 자동 적재 |
| `data/data_map.json` | 데이터 지도용 그래프 요약(`scripts/build_data_map.py`로 생성) |
| `data/regions.yaml`, `data/industries.yaml` | 지명 별칭·업종 별칭(B에서 가져옴) |

- 운영 환경에서는 센터 서버가 허브 자료를 보유한다고 가정합니다. 데모는 API와 미리 받은 파일로 계산합니다.
- 43개 읍면동을 하나씩 받습니다(처음 한 달치에 자료당 약 170~220회, 이후 캐시). 자료별 하루 900회에서 멈추고, 전체를 받지 못하면 받은 지역만 계산하고 순위 판정은 '참고'로 보류합니다.

## 시험

```
.venv\Scripts\python -m pytest -q tests
```

오프라인으로 jeju-agent 기대값을 재현합니다: 애월 카페 228·한림 152, 방문지표 1만당 8.32·11.41, 한림 편의점 59,
2026-08 노형동 230,606.48·연동 246,548.48, 지표 단위 합산 차단, 746 매장수를 지역 분모로 쓰지 않음, 미래 예측 질문 보류.

v2(정확도 개선) 시험 10개를 더해 모두 17개입니다: 시점 맞추기(746은 2021-05), 비교·추이 결론 문장, 개념 해설,
내부 메모 비노출, 그래프 자동 선택, 단순 질문의 관점 지표 2개 제한, 오래된 자료 경고, 모호한 동 이름 되묻기, 조건 2개 교차.

## 해석 확인 (v2.1)

- 결과 맨 위 '이렇게 이해했어요' 줄에 모델 해석(지역·측정값·나누는 기준·분석·기간·조건 방향)을 보여 주고, '해석 고치기'에서 바꿔 다시 계산할 수 있습니다.
- 코드 확인 단계가 질문에 근거 없는 값을 지우면, 질문 칸 아래에 무엇을 뺐는지 알려 줍니다.
- 모델 재점검: 1차 해석 뒤 같은 모델이 질문과 해석을 비교해 빠진 항목을 고칩니다(`agent/prompts/graph_review.md`). 기본은 꺼져 있습니다(평가 44문항: 켬 75%·9.1초, 끔 77%·3.6초). `.env`에 `INTERPRET_REVIEW=on`으로 켭니다.
- 업종 값은 업종 대응표나 상가 자료(허브 793)의 업종 이름에 있어야 남깁니다('외국인'·'버스' 같은 값은 지우고 알림).

## 모델 해석 평가 (v2)

```
.venv\Scripts\python scripts\eval_interpret.py
.venv\Scripts\python scripts\eval_interpret.py --no-review
```

`--cases eval/interpret_holdout.jsonl`은 프롬프트 수정에 쓰지 않은 별도 질문 15개(확인용)입니다. 프롬프트 예시는 `interpret_cases.jsonl`의 틀린 문항을 보고 고치므로, 실제 성능은 holdout 점수로 판단합니다.

`--no-review`는 재점검 없이 1차 해석만 잽니다. 두 결과를 비교해 재점검을 계속 쓸지 정합니다.

`eval/interpret_cases.jsonl`(44문항: 개수·밀도·비교·추이·순위·생활시설·답할 수 없는 요구·잡담·오타·모호 지명)을 로컬 모델로 해석해
지명·개념·구분값·분석 유형 정확도를 재고 `eval/interpret_report.md`에 저장합니다. 프롬프트를 바꿀 때마다 돌리고,
틀린 유형은 프롬프트 예시로 고칩니다(코드로 해석을 보정하지 않음). 목표: 전체 85%, 지명·개념 각 90%.

## 폴더

```
app.py                  화면(Streamlit, B 디자인)
agent/llm.py            Ollama 호출(B): JSON 스키마 강제, 재시도, 측정 로그(metrics/)
agent/prompts/graph_interpret.md   해석 프롬프트
graph/interpret.py      ① 해석 + 코드 가드 + LLM off 폴백
graph/lenses.yaml       ② 분석 관점(렌즈)
graph/engine.py         ③④ 자료 선택·템플릿 계획·검증·조회·집계
graph/pipeline.py       ⑤ 지표 구성·판정·사실 문장·질문 유형별 결론(lead_for)·조건 교차(cross_table)
graph/concept_notes.yaml   개념 해설(일상 말 ↔ 자료 뜻, 결론 아래 표시)
graph/charts.py         그래프와 자동 선택 규칙(choose_charts)
eval/                   모델 해석 평가 세트·보고서
graph/charts.py         그래프(plotly)
graph/access.py         허브 API·파일 접근
graph/kg.py             지식 그래프 조회(A의 kg_query)
tools/data_map.py       이 답변의 데이터 지도(vis-network, 오프라인)
tools/theme.py, tools/rank_areas.py   B 디자인·순위 계산
scripts/                데이터 지도 생성, 해석 점검
tests/                  오프라인 시험
```
