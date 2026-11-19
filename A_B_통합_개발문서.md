# 제주 데이터 상담 에이전트 — A·B 통합 개발 문서

- 작성: 2026-11-19 (목)
- 대상 레포
  - **A** = `jeju-agent` (joohayoung/jeju-agent): 지식 그래프로 데이터를 찾는 쪽
  - **B** = `jeju-analyst-poc` (YeongJuYJ/jeju-analyst-poc): 분석·시각화·화면 쪽
- **제출 마감: 2026-11-20 (금) 10:00** (DAKER, 마감 후 수정 불가)
- 이 문서만 보고 바로 개발을 시작할 수 있게 쓰는 것이 목표입니다. 결정된 것과 아직 정해야 할 것을 구분해서 적었습니다.

---

## 0. 한눈에 보기 — 확정된 결정

| # | 결정 | 근거 |
|---|---|---|
| D1 | **제품 레포는 B**입니다. A는 지식 그래프를 만드는 오프라인 도구로 남깁니다. | B가 센터 PC 사양에 맞춰져 있고, 반출 흐름·테스트·QA50 평가를 이미 갖추고 있음 |
| D2 | **화면과 화면에 보이는 콘텐츠는 B 그대로** 씁니다. | 팀 결정 |
| D3 | B 화면에 추가하는 것은 **"이 답변의 데이터 지도"(선별된 데이터 그래프) 하나**뿐입니다. 전체 데이터 지도 탭은 넣지 않습니다. | 팀 결정. 코드(`home_html`)는 있지만 화면에 연결하지 않음 |
| D4 | **LLM은 로컬 모델만** 씁니다. Ollama + **qwen3:4b**(주 모델, `think=false`)를 쓰고, kanana-2.1b를 폴백으로 둡니다. | 운영 중 외부 API는 쓰지 않음. GPT는 그래프를 처음 한 번 만들 때만 썼음 |
| D5 | **데이터 선별은 A 방식으로 합니다.** LLM이 정해진 지시문에 따라 질문에서 키워드(슬롯)를 뽑고, **코드**가 그래프에서 후보 데이터를 추립니다. | 2~4B 모델은 그래프 전체를 입력으로 받을 수 없음. 개념 어휘 이름만 넣으면 1,051자라 들어감 |
| D6 | **B의 분석부를 범용으로 확장합니다.** A의 계산 방식(정해진 op, 계획, 검증)을 가져와서 B의 판정 틀(43개 동 순위·중앙값·상하위 25%)로 보여줍니다. | B는 지표마다 데이터가 고정돼 있어서, 처음 보는 데이터는 계산할 수 없음 |
| D7 | **분석 계획 단계는 제한합니다.** 후보는 최대 3개, 카드는 축소, 단순한 질문은 코드 템플릿으로 계획하고, LLM은 애매한 경우에만 씁니다. op는 정해진 목록에서만 고르고, 검증에 실패하면 1회 재계획하고 그래도 안 되면 보류합니다. | 4B 모델의 컨텍스트와 정확도 한계 |
| D8 | **B의 기존 경로는 건드리지 않습니다.** 창업 검증, 데이터 탐색, 그날의 제주, 넓은 질문이 대상입니다. 범용 경로(G 경로)는 **B가 답하지 못하는 질문만** 받습니다. | B의 QA50 결과(양호 41, 오답 0)를 지키기 위해 |
| D9 | 데이터 보유는 **"운영 시 센터 서버가 허브 전체를 보유한다"고 가정**합니다. 데모는 API와 미리 내려받은 데이터만 씁니다. 기획서에 이 가정을 명시합니다. | 팀 결정 |
| D10 | **LLM은 숫자를 만들지 않습니다.** 모든 수치는 코드가 계산하고, 문장 속 숫자는 결과 표와 다시 대조합니다. | A와 B의 공통 원칙 |

---

## 1. 배경: 두 프로젝트 비교 (코드를 읽고 확인한 내용)

| | A (jeju-agent) | B (jeju-analyst-poc) |
|---|---|---|
| 성격 | 범용 데이터 상담 | 창업 검증 전문 분석관 |
| 데이터 범위 | 허브 **1,259종**을 지식 그래프로 연결 | 직접 정제한 **17종**(허브 12 + 외부 6) |
| 데이터 선택 | 질문 → 개념 → 그래프(개념→컬럼→데이터) → 결합 확인 → LLM 계획 | **선택하지 않음.** 메뉴와 지표(I1~I12)가 쓸 데이터와 계산식을 미리 정해둠 |
| 분석 깊이 | 얕음(count/sum/mean/daily_mean + 비율 1회) | 깊음(43개 동 순위·판정, 추이·계절성·생존율 등) |
| LLM | GPT-5 mini(외부 API) | Ollama 로컬 모델(kanana 2.1B, 폴백 qwen3:4b) |
| UI | 표준 라이브러리 서버 + ECharts·vis-network | Streamlit + plotly, HTML 리포트, png |
| 추가 기능 | 데이터 지도, 결합 불가 사유, 추가 자료 요청서 | 반출 점검·운영자 화면, 이어서 묻기, 폼 모드(LLM 꺼도 동작) |
| 검증 | 10문항 10/10 | QA50: 양호 41 / 부분 3 / 오답 0 / 정직한 불가 6, pytest 20개 이상 |

**같은 결과가 독립적으로 재현됐습니다.** 애월 카페 경쟁 밀도 **8.32**(방문 1만당)가 A와 B에서 똑같이 나왔습니다. 기획서에 교차 검증 근거로 쓸 수 있습니다.

---

## 2. 목표 구조

```
                     ┌──────────────── B 화면(Streamlit) ────────────────┐
질문 ─▶ [B] 조건 추출(extract_slots, 기존) ─▶ 라우팅
                                   │
         ┌─────────────────────────┴──────────────────────────┐
         ▼ (B가 답할 수 있음: 기존 메뉴)                             ▼ (B가 답할 수 없음: §5.1 진입 조건)
   [B 기존 경로 — 변경 없음]                                    [G 경로 — 신규]
   창업 검증 / 데이터 탐색 / 그날의 제주 / 넓은 질문                  G1 질문 해석(LLM, 어휘 162개 안에서만)
   지표 I1~I12 → 판정 → 그래프·리포트·반출                         G2 그래프 후보 선별(코드, 최대 3개)
         │                                                     G3 분석 계획(템플릿 우선, LLM 제한적)
         │                                                     G4 검증(코드, A 규칙 + 추가 규칙)
         │                                                     G5 조회·계산(코드, 43개 동 전체)
         │                                                     G6 B형 결과로 변환(IndicatorResult)
         │                                                     G7 문장(코드 사실 문장 + 다듬기 가드)
         ▼                                                              ▼
   B 결과 화면 + ★이 답변의 데이터 지도★              B 결과 화면(같은 부품) + ★이 답변의 데이터 지도(후보·제외 사유 포함)★
                                   │
                              반출 점검(B 기존)
```

- 지식 그래프(`kg.sqlite`)는 **A에서 오프라인으로 한 번 만들어 B에 복사**합니다. 운영 중에는 조회만 합니다.
- G 경로 결과도 B의 `IndicatorResult`로 바꾸기 때문에, B의 판정(`judge.table`), 그래프(`position_chart`), 리포트, 반출 점검을 **그대로 재사용**합니다.

---

## 3. 일정과 우선순위 (마감 11/20 10:00 기준)

| 우선순위 | 작업 | 문서 위치 | 완료 기준 |
|---|---|---|---|
| **P0** (오늘) | 0단계: Ollama qwen3:4b 띄우고 B를 qwen3:4b로 실행 | §4 | B의 대표 질문이 qwen3:4b로 끝까지 돌아감 |
| **P0** | 1단계: 데이터 해석 불일치 2건 정리(746 매장수, visitPop 단위) | §5.0 | 검증 코드 결과로 결정하고 B 코드·문구에 반영 |
| **P0** | 2단계: "이 답변의 데이터 지도" 연결 | §6 | 창업 진단 결과 아래 지도 표시(코드 완료, B PC에서 실행 확인만 남음) |
| **P0** | 3단계(최소): G 경로를 **API 데이터 + 템플릿 계획(T1·T2·T4)**으로 데모 질문 3개 통과 | §7 | §9.3 데모 질문 3개 통과 |
| **P0** | 기획서 반영 | §10 | 구조도, 가정, 범위 문구 |
| P1 (마감 후) | G 경로 LLM 계획, trend/share 템플릿, 파일 데이터, 반출 기본 규칙 | §7 | §9 평가 기준 |
| P2 | 법정동 매핑 통일, 허브 클라이언트 통일, 개념 807개 검수, B 지표를 그래프 개념과 연결 | §12 | — |

> 시간이 모자라면 **P0의 G 경로는 "후보 데이터와 데이터 지도만 보여주고 계산은 보류"**로 줄입니다. 이 경우 G2 결과를 데이터 지도와 결합 불가 사유로 보여주는 것만으로도 "B가 답하지 못하던 질문을 안내로 바꾼다"는 가치가 생깁니다.

---

## 4. 0단계: 로컬 모델 준비

### 4.1 PC별 상황

| | 개발 PC | 센터 운영 PC(대회 최소사양) |
|---|---|---|
| GPU | RTX 2070 SUPER, **전용 VRAM 8GB** (작업 관리자의 24GB는 공유 메모리 포함 값) | GTX 1060, VRAM 3GB |
| RAM / CPU | 32GB / Ryzen 9 3900X(12코어) | 32GB / i7-8700(6코어) |
| qwen3:4b (약 3.2GB, B 측정) | **전부 GPU에서 실행** | 3GB를 넘어서 일부 레이어를 CPU로 넘김(느려짐) |

- **정확도**는 같은 모델이라 개발 PC 결과를 그대로 믿어도 됩니다.
- **속도**는 센터 PC 조건을 흉내 내서 따로 재야 합니다(§4.4).

### 4.2 설치와 확인 (터미널에 붙여 넣기)

```
ollama pull qwen3:4b
ollama run qwen3:4b --think=false "애월에 카페가 너무 많을까요? 지역과 업종만 JSON으로 답해"
ollama ps
```

- `ollama ps`의 PROCESSOR 칸이 `100% GPU`면 정상입니다.
- kanana-2.1b는 B 쪽 PC에 이미 `ollama create`로 등록돼 있습니다(B `POC_RESULT.md` §2). 개발 PC에서도 폴백을 시험하려면 같은 GGUF로 등록하세요.

### 4.3 B 설정(.env)

```
OLLAMA_MODEL=qwen3:4b
LLM_MODE=on
HUB_PROJECT_KEY=허브_프로젝트_키
```

- B의 `agent/llm.py`는 모델 이름이 `qwen3`로 시작하면 이미 `think=false`를 넣습니다(코드 확인함). 따로 고칠 것은 없습니다.
- 기본 옵션은 `temperature 0, seed 42, num_ctx 4096, num_predict 300`입니다. **G3 계획 호출만 `num_ctx 6144`, `num_predict 500`**으로 올립니다(§7.4 토큰 예산 참고).

### 4.4 센터 PC 흉내 측정

B의 `llm.py`에 이미 측정용 옵션이 있습니다.

```
OLLAMA_NUM_GPU=20
OLLAMA_NUM_THREAD=6
```

- `OLLAMA_NUM_GPU`는 GPU에 올리는 레이어 수입니다. 3GB 상황을 흉내 내려면 qwen3:4b 전체 레이어(36개) 중 일부만 올립니다. 시작값 20에서 `ollama ps`의 GPU 비율이 약 85~90%가 되도록 조정하세요.
- `OLLAMA_NUM_THREAD=6`은 i7-8700의 6코어를 흉내 냅니다.
- 측정 결과는 `metrics/llm_calls.jsonl`에 쌓입니다. §9의 성능 표에 옮깁니다.

---

## 5. 데이터 해석 맞추기와 G 경로 진입 조건

### 5.0 데이터 해석 불일치 2건 (P0, 제출 전 반드시 정리)

같은 데이터를 A와 B가 따로 검수하면서 결론이 갈렸습니다. 한 서비스 안에서 서로 모순되면 심사 중 재검증에서 바로 드러납니다.

| 항목 | A의 결론(`지식그래프/verified_overrides.json`) | B의 처리 | 영향 |
|---|---|---|---|
| **746 `매장수`** | "같은 년월·업종 안에서 **지역과 무관하게 같은 값** → 업종 전체 매장 수. 지역 분모로 쓰면 안 됨" | (월, 시, 법정동, 업종)마다 대표값으로 보고 **I7 점포당 카드 매출의 분모**로 사용 | A가 맞으면 **B의 I7은 성립하지 않음** |
| **583 `visitPop` 단위** | 단위는 '지표'. 고유 방문객 수가 아님. **'명'을 붙이지 않고 '방문지표'로 표기**, 여러 날을 더하지 않음 | "일평균 방문 314,040**명**" | 화면 문구와 리포트 단위 |

참고로 B의 "(월, 시, 법정동, 업종) 안에서 한 값"이라는 확인은 A의 결론과 모순되지 않습니다. 핵심은 **같은 월·업종에서 법정동끼리 값이 다른가**입니다. 아래 코드로 확인하세요(B 폴더에서 실행).

```python
import glob, pandas as pd
files = [f for f in glob.glob("data/raw/files/card_emd/*.csv") if "(1)" not in f]
df = pd.concat([pd.read_csv(f, encoding="cp949", usecols=["년월", "시도명", "읍면동명", "업종명", "매장수"]) for f in files])
df = df.drop_duplicates(["년월", "시도명", "읍면동명", "업종명", "매장수"])
per_area = df.groupby(["년월", "업종명"])["매장수"].nunique()
print("같은 년월·업종 안에서 법정동별 매장수 종류 수 분포")
print(per_area.value_counts().head(10))
print("법정동마다 다른 값이 있는 (년월, 업종) 비율:", round((per_area > 1).mean() * 100, 2), "%")
cafe = df[(df["년월"] == df["년월"].max()) & df["업종명"].str.contains("커피|카페|비알코올", na=False)]
print(cafe.groupby("업종명")["매장수"].agg(["nunique", "min", "max"]))
```

**판단 규칙**

- 법정동마다 다른 값이 있는 비율이 **5% 미만**이면 A의 결론이 맞습니다. 이 경우 처리는 이렇습니다.
  - I7은 **확인 불가**로 바꾸고, 사유에 "매장수가 업종 전체 값이라 동네별 점포당 매출을 계산할 수 없음(허브 746)"이라고 적습니다.
  - 대안으로 "동네별 카드 이용금액 순위"는 분모 없이 쓸 수 있습니다.
- 비율이 높으면 B의 처리를 유지하고, A의 `verified_overrides.json`에서 `746.매장수`의 `denominator_scope`를 지운 뒤 그래프를 다시 만듭니다(`kg_stage4_merge.py`).

**visitPop 처리**

A의 근거(허브가 가공해 제공하는 방문지표)를 따라 **"방문지표"로 통일**하는 것을 권합니다. 고칠 곳은 B의 `indicators/changup.yaml`(I1 단위 `명/일`, I3 단위 `점포/방문인구 1만 명`), `tools/report.py`의 단위 표기, 리포트 템플릿입니다.

### 5.1 G 경로 진입 조건 (라우팅)

B의 `Session.start()` → `_normalize()` 다음, `app.py`의 `next_stage()`에서 결정합니다.

| 조건 | 현재 B 동작 | 바뀐 동작 |
|---|---|---|
| `menu == "창업 검증"`이고 지역·업종 정상 | 창업 진단 | **그대로** |
| `menu`가 데이터 탐색, 그날의 제주, 업종 동향, 입지 추천, 업종 비교, 지표 순위, 시 비교, 사건 영향, 접근성 | 각 경로 | **그대로** |
| `menu == "안내"`이고 `broad.unsupported_reason(question)`이 **있음**(주식, 날씨예보 등 명시적 범위 밖) | 안내 문구 | **그대로**(G 경로로 보내지 않음) |
| `menu == "안내"`이고 `unsupported_reason`이 **없고**, `broad.guide()` 결과 `kind == "안내"` | 안내 문구(막다른 길) | **G 경로** |
| `menu in ("모름", "상권 진단")` | 오류 문구 | **G 경로** |
| `error`가 "업종 대응표 없음"이나 "업종을 찾지 못함" | 오류 문구 | **G 경로** |
| `error`가 "지역을 정하지 못함" | 오류 문구 | **그대로**(지역 되묻기가 먼저) |
| `error == "form_needed"`(LLM 꺼짐 또는 실패) | 폼 | **그대로** |

구현은 이렇게 합니다.
- `Session`에 `graph_result` 필드를 추가합니다.
- `next_stage()`에 `"graph"`를 추가합니다.
- G 경로로 보낼 때도 B의 `_unanswered()` 기록은 남깁니다. 운영자 탭의 "답하지 못한 질문"이 G 경로 개선 목록이 됩니다.

---

## 6. 2단계: "이 답변의 데이터 지도" (코드 완료)

### 6.1 만든 것 (이 폴더의 `데이터지도_코드/`)

| 파일 | 역할 |
|---|---|
| `scripts/build_data_map.py` | A의 `kg.sqlite`에서 지도에 필요한 부분만 뽑아 `data/data_map.json`(917KB)으로 저장합니다. 자료 1,259 · 이름 444 · B가 쓰는 허브 자료 사이의 결합 40쌍이 들어갑니다. 표준 라이브러리만 씁니다. |
| `tools/data_map.py` | `answer_graph()`, `answer_html()`, `show_answer()`. vis-network를 인라인으로 넣어 **오프라인에서 그립니다**. `st.iframe`이 있으면 그걸 쓰고, 없으면 `components.html`을 씁니다. |
| `tools/vendor/vis-network.min.js` + 라이선스 2개 | MIT/Apache-2.0. 기획서의 오픈소스 목록에 추가해야 합니다. |
| `data/data_map.json` | 빌드 결과물 |
| `app_py.diff` | B `app.py` 수정분(import 1줄 + 진단 결과 아래 섹션 1개) |

### 6.2 표시 규칙

| 요소 | 모양 |
|---|---|
| 이 답변에 쓴 자료 | 주황 원(굵은 테두리) |
| 검토했지만 쓰지 않은 자료(G 경로) | 회색 원. 클릭하면 `[사용하지 않음] 사유`가 먼저 보임 |
| 알 수 있는 것(개념) | 연청록 원(자료당 최대 2개) |
| 지역 | 연주황 원(읍면동이나 법정동 단위 자료에만 연결) |
| 결합 가능 | 주황 굵은 선. 라벨은 `결합 읍면동 · 2025-09~` |
| 클릭 | 설명, 허브 ID, 기간, 주제 태그, "허브에서 원자료 보기" 링크 |

애월 카페 예시로 확인한 결과는 이래요. 583–793과 583–746은 결합 선이 이어지고, **746–793은 선이 없습니다**(기간 불일치). A의 판단이 지도에 그대로 드러납니다.

### 6.3 B에 넣는 위치

- **창업 진단**: `show_diagnosis()` 끝의 "쉬운 말 요약" 다음입니다(diff 그대로). 쓴 자료는 `sel[*].sources[*].hub_id`에서 가져오고, 지역은 `[s.area, *s.compare]`입니다.
- **G 경로 결과**: `show_graph_result()` 안에서 `data_map.show_answer(used_ids, places, candidates={hub_id: 제외 사유})`로 부릅니다.
- **넓은 질문과 그날의 제주**: 결과 dict에 출처 허브 번호가 있으면 같은 방식으로 붙입니다(P1).
- 그래프에 없는 번호(외부 데이터, 공공데이터포털)는 자동으로 건너뛰고, 아무것도 없으면 캡션만 표시합니다.

### 6.4 그래프를 다시 만들 때 (A에서)

```
python -X utf8 지식그래프/kg_stage4_merge.py
python scripts/build_data_map.py 경로/jeju-agent/지식그래프/kg.sqlite
```

- 두 번째 명령은 B 폴더에서 실행합니다.
- `build_data_map.py`의 `B_HUB_IDS`는 B의 `tools/provenance.py` 출처 목록과 맞춰야 합니다. G 경로가 쓰는 자료가 늘면 이 목록 대신 "모든 결합 관계"를 담도록 바꿉니다(P1, 용량 확인 필요).

### 6.5 확인한 것과 남은 것

- 확인: 독립 HTML과 Streamlit 1.67 안에서 렌더링, 후보 노드 표시, JS 오류 없음.
- 남음: **B의 실제 진단 화면에서 한 번 실행해서 확인**하기. 원자료와 Ollama가 있는 PC에서 해야 합니다.

---

## 7. 3단계: G 경로(범용 분석) 상세 설계

### 7.0 새 파일 배치(B 레포)

```
graph/
  __init__.py
  kg_query.py        A의 지식그래프/kg_query.py 복사(DB 경로만 data/kg.sqlite로)
  vocab.py           검수 어휘 162개 + 동의어 사전 로드(kg.sqlite에서 status='어휘'만)
  interpret.py       G1 질문 해석(LLM) + 코드 가드
  search.py          G2 그래프 후보 선별(코드)
  cards.py           G3용 축소 카드 생성
  plan.py            G3 템플릿 계획 + 제한된 LLM 계획
  validate.py        G4 A의 validate 포팅 + 추가 규칙
  access.py          G5 데이터 접근(API: B hub/client 재사용 + 페이징 / 파일: data/hub_data.db)
  execute.py         G5 pandas 집계(43개 동 전체)
  to_indicator.py    G6 결과 → B IndicatorResult
  narrate.py         G7 사실 문장(코드) + 다듬기 가드
  pipeline.py        run_graph(question, b_slots) → GraphResult
agent/prompts/graph_interpret.md
agent/prompts/graph_plan.md
agent/schemas.py     GraphSlots, GraphPlan 추가
data/kg.sqlite       A에서 복사(17MB). .gitignore 여부는 팀 결정(대회 규정상 참가자 목록 번호 열은 이미 제거된 파일)
```

### 7.1 G1 질문 해석 (LLM + 코드 가드)

**입력 예산**: 시스템 프롬프트(규칙과 예시 약 1,200자) + 어휘 이름 162개(**1,051자, 실측**) + 질문. 4096 컨텍스트 안에 들어갑니다.

**스키마 (`agent/schemas.py`)**: 개념은 어휘 목록으로 **enum을 강제**합니다. Ollama `format`의 문법 제약이 적용돼서, 어휘 밖의 단어는 출력 자체가 안 됩니다.

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field, create_model
from graph.vocab import MEASURE_NAMES, DIM_NAMES

Measure = Literal[tuple(MEASURE_NAMES)]
Dim = Literal[tuple(DIM_NAMES)]
Analysis = Literal["count", "sum", "mean", "ratio", "compare", "trend", "share", "rank", "lookup"]

class GFilter(BaseModel):
    concept: Dim
    value: str

class GRatio(BaseModel):
    numerator: Measure
    denominator: Measure
    scale: int = 10000

class GPeriod(BaseModel):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

class GraphSlots(BaseModel):
    places: list[str] = Field(default_factory=list, max_length=4)
    concepts: list[Measure] = Field(min_length=1, max_length=3)
    filters: list[GFilter] = Field(default_factory=list, max_length=3)
    period: Optional[GPeriod] = None
    analysis: Analysis
    ratio: Optional[GRatio] = None
    unsupported: str = ""
```

`SCHEMAS["graph_interpret"] = GraphSlots`로 등록합니다.

**프롬프트 (`agent/prompts/graph_interpret.md`)**: A의 `SLOT_SYS`를 4B 모델용으로 줄인 판이에요.

```
### system
너는 제주 도민의 데이터 질문을 분석 조건으로 바꾼다. JSON 하나만 출력한다.
- places: 질문에 나온 지명 그대로. 없으면 [].
- concepts: 알고 싶은 '측정값'. 아래 측정값 목록의 이름 그대로 1~3개.
- filters: 업종·연령대·국적처럼 나누는 기준과 그 값. concept는 아래 구분값 목록 이름, value는 질문 속 낱말 그대로(예: 카페).
- period: 질문에 날짜·연월이 있을 때만. 없으면 null. 날짜를 지어내지 않는다.
- analysis: 개수 count, 합계 sum, 평균 mean, 비율·밀도 ratio, 지역끼리 비교 compare, 시간에 따른 변화 trend, 구성비 share, 순위 rank, 값 하나 lookup.
- 가게·점포·매장 수는 '점포수', 유동인구·방문객 규모는 '방문인구', 매출은 '카드이용금액'.
- '많을까요', '경쟁이 심한가'처럼 밀집도를 물으면 analysis=ratio, ratio={numerator:'점포수', denominator:'방문인구', scale:10000}.
- 미래 예측, 순이익, 개인 정보처럼 데이터로 답할 수 없는 요구는 unsupported에 적는다.

측정값: {measures}
구분값: {dims}

예시
질문: 애월에 카페 너무 많을까요? 한림보다 경쟁이 심한지 궁금해요.
{"places":["애월","한림"],"concepts":["점포수","방문인구"],"filters":[{"concept":"업종","value":"카페"}],"period":null,"analysis":"ratio","ratio":{"numerator":"점포수","denominator":"방문인구","scale":10000},"unsupported":""}

질문: 2024년 1월 1일 제주 관측소들의 평균기온
{"places":[],"concepts":["기온"],"filters":[],"period":{"start":"2024-01-01","end":"2024-01-01"},"analysis":"mean","ratio":null,"unsupported":""}

### user
질문: {question}
```

**코드 가드 (`graph/interpret.py`)**: 순서대로 적용하고, 각 가드는 B의 `_step(... guards)`에 기록합니다.

1. **날짜**: 질문에 B의 `DATE_HINT` 패턴이 없으면 `period`를 버립니다(B 방식).
2. **지명**: `places`를 B의 `normalize_region()`으로 행정동에 맞춥니다. 실패하면 `KG.place()`로 시도하고, 유사도 0.6 미만이면 **되묻기**를 합니다("노현동 → 노형동인가요?").
3. **개념 보충**: 질문에서 동의어 사전(`vocab.syn`, 검수 어휘만)으로 찾은 개념이 LLM 출력에 없으면 추가합니다(최대 3개).
4. **업종 필터**: 질문에 B `industries.yaml` 별칭이 있으면 `filters`에 `{"업종": 표준 업종명}`을 넣거나 고칩니다.
5. **비율 보정**: `analysis == "ratio"`인데 `ratio`가 null이면 concepts의 앞 두 개로 채웁니다(분자는 점포수·건수 계열, 분모는 인구 계열).
6. `unsupported`가 비어 있지 않으면 G 경로를 멈추고 B의 안내 형식으로 답합니다.

**LLM_MODE=off일 때**: 3·4·5번 코드 규칙만으로 슬롯을 만듭니다. concepts가 비면 G2를 FTS(`dataset_fts`)로 돌려서 후보 목록과 데이터 지도만 보여줍니다.

### 7.2 G2 그래프 후보 선별 (코드만)

```python
from graph.kg_query import KG
g = KG("data/kg.sqlite")
found = g.find_datasets(slots.concepts, place_level="읍면동", period=slots.period, top=5)
pairs = g.plan_pairs(found)
```

`find_datasets`는 A에 이미 있는 기능이에요. 개념 → MEASURES → 컬럼 → HAS_COLUMN → 데이터 경로와, ABOUT 주제 경로로 후보를 모읍니다. 이후 처리는 이렇습니다.

1. **지역 단위로 거르기**: 질문이 읍면동 단위인데 자료가 시군구·시도 단위로 더 거칠면 제외합니다. 법정동이면 변환 표시를 붙입니다.
2. **기간으로 거르기**: 검증된 실제 기간(`auto_update_verified_end` 우선)과 겹치지 않으면 제외하고 사유를 기록합니다.
3. **이용 가능성으로 거르기**(신규): 데모에서는 `access`에 API가 포함되고 dataKey가 있거나, `data/hub_data.db`의 `hub_catalog`에 해당 허브 번호 표가 있는 자료만 계산 후보로 씁니다. 나머지는 "운영 시 센터 서버 데이터로 계산"이라는 사유로 **지도에만** 표시합니다(D9).
4. **정렬**: 검증 여부 → 분모 범위 주의 없음 → 최신 기간 → 결합 관계 수 순서입니다.
5. **최종 후보는 개념당 1~2개, 전체 최대 3개**입니다. 나머지는 `candidates_rejected = {hub_id: 사유}`로 지도에 넘깁니다.
6. 비율 분석인데 분자와 분모 자료 사이에 JOINABLE이 없으면, 계산 단계로 넘기지 않고 **"결합 불가: 사유"**로 보류합니다. 지도에는 두 자료를 회색으로, 사유와 함께 표시합니다.

**B의 17종 우선 규칙**: 후보 중 B 어댑터가 있는 자료(583, 589, 746, 793, 1048, 495, 780)는 B의 정제 테이블(`agg_*`)을 우선 쓰도록 `access.py`에서 분기합니다. 중복, 글자 깨짐, 법정동 매핑 같은 B의 정제 결과를 그대로 활용하기 위해서예요.

### 7.3 G3 분석 계획 — 템플릿 우선, LLM은 제한적으로 (D7)

#### 7.3.1 op 목록 (이 밖은 금지)

| op | 뜻 | 적용 조건 |
|---|---|---|
| `count` | 행 수(개체 목록: 1행 = 점포 1개) | 측정 컬럼 없이 개체 목록 자료 |
| `sum` | 합계 | 단위가 명·원·건이고, 단위가 '지표'가 아님 |
| `mean` | 평균 | 단위가 %·율·지수·℃ 등 |
| `daily_mean` | 날짜별 합계의 평균 | 단위가 '지표'이거나, 일 단위 인구 자료 |
| `ratio` | 단계 2개의 비율 × scale | 두 자료가 JOINABLE이거나 같은 자료 |
| `trend` | 월별 group_by(시간키) | analysis가 trend |
| `share` | 구분값별 구성비(%) | analysis가 share |

#### 7.3.2 코드 템플릿 (LLM 호출 없음)

| 템플릿 | 조건(모두 만족) | 만드는 계획 |
|---|---|---|
| **T1 개수** | 후보 1개, 측정 컬럼 없는 개체 목록, 필터 값이 한 컬럼에 **정확히** 존재 | `count` + 필터 + 지역 키 |
| **T2 규모** | 후보 1개, 측정 컬럼 1개, 단위 규칙으로 op 결정 가능 | `sum`/`mean`/`daily_mean` + 기간 + 지역 키 |
| **T4 밀도·비율** | slots.ratio 있음, 분자와 분모가 각각 T1이나 T2로 풀림, 두 자료가 JOINABLE | 단계 2개 + `ratio` |
| T5 추이(P1) | analysis=trend, 시간키 1개 | T2 + `group_by=시간키(월)` |
| T6 구성비(P1) | analysis=share, 필터 대상 구분값 컬럼 1개 | T2 + `group_by=구분값`, 제주 전체 |

**단위 → op 규칙**

| 단위 | op |
|---|---|
| '지표' | `daily_mean` |
| %, 율, 지수, ℃, mm | `mean` |
| 명, 원, 건, 개, 대 | 기간이 1일이면 값 그대로, 아니면 `sum` |
| 측정 컬럼 없음(개체 목록) | `count` |

**기간 기본값**: 질문에 기간이 없으면 이렇게 정합니다.
- 시계열 자료는 **검증된 최신 달 1개월**이에요(예: 583은 2026-08).
- 스냅샷 자료와 함께 쓰면 **스냅샷 날짜가 속한 달**이에요(A 규칙: 793 2025-09-18이면 583 2025-09).
- 화면에 "기간을 말하지 않아 최신 달로 계산"이라고 표시합니다.

**필터 값 확인**: 질문 값(예: 카페)이 어느 구분값 컬럼에 **정확히** 있는지 코드로 찾습니다(A `file_values`, B 정제 테이블). 정확한 값이 컬럼 하나에만 있으면 템플릿으로 진행합니다. **'카페'에 '독서실/스터디 카페' 같은 비슷한 값은 더하지 않습니다**(A 규칙).

#### 7.3.3 LLM 계획을 쓰는 경우 (P1)

다음 중 하나일 때만 씁니다.
- 같은 개념을 재는 측정 컬럼이 후보 안에 2개 이상 있음
- 필터 값이 여러 구분값 컬럼에 정확히 있음
- 후보 자료 점수 차이가 작아서 어느 쪽을 쓸지 정해지지 않음

**축소 카드 규격 (`graph/cards.py`)**

- 컬럼: 매칭된 측정 컬럼 + 선택된 공간키 1개 + 시간키 1개 + 필터 대상 구분값만, **최대 6개**
- 컬럼마다 `name, role, unit, grain, ex(예시값 최대 3개), note`만 넣음
- 자료당 **약 600자 이하**. 축소 전 실측은 583이 1,083자, 793이 1,727자, 746이 1,528자예요.
- 카드 3개 + 규칙 약 1,500자 + 슬롯 → `num_ctx 6144`로 호출

**스키마**: `GraphPlan`은 A의 `PLAN_SYS` 출력을 그대로 쓰되 op를 enum으로 제한하고, chart 필드는 뺍니다(그래프는 B 방식으로 코드가 정함).

```python
class GMeasure(BaseModel):
    op: Literal["count", "sum", "mean", "daily_mean"]
    column: Optional[str] = None
    time_column: Optional[str] = None

class GStep(BaseModel):
    id: Literal["s1", "s2"]
    dataset: int
    measure: GMeasure
    filters: dict[str, list[str]] = Field(default_factory=dict)
    place_column: Optional[str] = None
    group_by: Optional[str] = None

class GCombine(BaseModel):
    op: Literal["none", "ratio"]
    numerator: Optional[Literal["s1", "s2"]] = None
    denominator: Optional[Literal["s1", "s2"]] = None
    scale: int = 1

class GraphPlan(BaseModel):
    steps: list[GStep] = Field(min_length=1, max_length=2)
    combine: GCombine
    period: Optional[GPeriod] = None
    reason: str
```

실패 처리는 이래요. 검증(G4) 오류 목록을 붙여서 **1회 재계획**하고, 그래도 실패하면 **계산 보류**로 처리합니다. 보류할 때는 후보 데이터와 지도, 보류 사유, 추가 자료 요청서를 보여줍니다.

### 7.4 토큰 예산 요약

| 호출 | 입력(대략) | num_ctx / num_predict |
|---|---|---|
| G1 해석 | 규칙·예시 약 1,200자 + 어휘 1,051자 + 질문 | 4096 / 300 |
| G3 계획(LLM일 때만) | 규칙 약 1,500자 + 카드 최대 3개 × 600자 + 슬롯 | **6144 / 500** |
| G7 다듬기(선택) | 사실 문장 2개씩(B 방식) | 4096 / 300 |

### 7.5 G4 검증 (`graph/validate.py`)

A의 `validate()`를 그대로 포팅하고, 아래 규칙을 추가합니다.

| 규칙 | 출처 |
|---|---|
| 자료가 G2 후보 안에 있어야 함 | A |
| 원자료가 있어야 함(데모: API 또는 hub_data.db) | A + D9 |
| 컬럼과 필터 값이 실제로 있어야 하고, 질문과 정확히 같은 값만 써야 함 | A |
| 요청 기간이 자료 기간 안에 있어야 함 | A |
| '지표' 단위는 여러 날 합산 금지(daily_mean 강제) | A |
| ratio의 두 자료는 JOINABLE이어야 함 | A |
| `denominator_scope`가 있는 컬럼(예: 746 매장수)은 지역 분모로 쓰지 않음 | A |
| 지역 컬럼은 행정구역 키여야 하고, group_by는 구분값이나 시간키여야 함 | A |
| **(추가)** 지역 순위 판정을 하려면 43개 동 중 **값이 있는 동이 10개 이상**이어야 함 | B의 분모 10 미만 확인 불가 규칙과 맞춤 |
| **(추가)** 법정동 자료는 MAPS_TO 비중으로 행정동 변환. 여러 행정동에 걸친 법정동이 결과 동에 포함되면 `notes`에 표시 | A 방식 + B 사유 표기 |
| **(추가)** 상호명·주소·좌표 컬럼은 측정, 필터, 출력에 쓰지 않음 | B `SENSITIVE` 규칙 |

### 7.6 G5 조회와 계산 (`graph/access.py`, `graph/execute.py`)

**데이터 접근**

- **API**: B의 `hub/client.fetch(code, params)`를 재사용합니다. 키 마스킹, 캐시, 데이터별 하루 1,000회 쿼터가 이미 들어 있어요. 그래프 자료는 `code = f"hub{hub_id}"`로 쓰고, `client.DATA_KEYS[code] = kg 노드의 data_key`를 실행 중에 등록합니다. 페이징은 A 방식으로 `limit=100`, `number=1..N`, `hasMore=false`까지 반복합니다. 쿼터 기준은 A처럼 **900회에서 멈춥니다**(여유분).
- **파일**: B의 `data/hub_data.db`(`hub_catalog`, 표 이름 `f{허브번호}_{순번}`)에서 읽습니다. 표가 여러 개면 컬럼이 맞는 표를 고릅니다.
- **B 어댑터가 있는 자료**: B의 정제 결과를 우선 씁니다(§7.2).

**계산 규칙**

- **43개 동 전체를 계산합니다.** 질문 지역만 계산하지 않습니다. B 판정(순위, 중앙값, 25%)을 쓰기 위해서예요. API는 `emd` 파라미터 없이 기간 전체를 받습니다.
- pandas로 구현하고, A의 `aggregate()` 의미를 그대로 따릅니다. 특히 `daily_mean`은 날짜별로 먼저 합하고 그다음 평균을 냅니다.
- 결과는 `pd.Series(index=행정동, values)`입니다. 값이 없는 동은 NaN으로 두고 사유를 기록합니다.
- 비율은 `분자 / 분모 × scale`입니다. 분모가 0이거나 NaN이면 NaN이고 사유는 "분모 없음"이에요.
- trend는 `DataFrame(index=월, columns=[대상 동, 제주 전체])`로 만들고, share는 `Series(index=구분값, %)`로 만듭니다.

### 7.7 G6 B형 결과로 변환 (`graph/to_indicator.py`)

```python
IndicatorResult(
    id="G1",                                   # 같은 답변 안에서 G1, G2 …
    name="방문지표 1만당 카페 점포 수",            # 코드가 개념·필터·ratio로 생성
    unit="점포/방문지표 1만",                     # 카드 unit으로 생성
    direction="none",                          # ★자동 지표는 항상 none → 판정은 높음·보통·낮음(유리·불리 금지)
    values=series_43,                          # index=행정동
    reasons=area_reasons,
    global_reason=None or "보류 사유",
    period="2025-09 (상가 2025-09-18 기준)",
    sources=[{"code": f"hub{id}", "name": 제목, "hub_id": id, "period": 기간,
              "collected_at": 캐시 시각, "external": False}],
    filters="상권업종소분류명=카페",
    notes=[주의사항들(cautions, 법정동 변환, 기간 기본값)],
    extra={"auto": True, "plan": plan, "trend": df or None, "share": s or None},
)
```

- 이렇게 만들면 B의 `judge.table()`, `report.position_chart()`, `report.fact_sentences()`, `render_html()`, 반출 점검을 **수정 없이** 쓸 수 있습니다.
- **`direction="none"`**으로 두는 이유가 있어요. 그래프가 자동으로 만든 지표에 "유리·불리"라는 가치 판단을 붙이지 않기 위해서입니다. B의 `quartile_label`이 이미 none일 때 "높음·낮음"을 돌려줍니다.
- 제주 전체 단일값(`lookup`, 지역 없음)이면 `scalar`에 넣고, 판정 표 대신 KPI 하나로 보여줍니다.

### 7.8 G7 문장 (`graph/narrate.py`)

1. B의 `report.fact_sentences(rows, results, area, label)`로 **코드가 사실 문장**을 만듭니다. 숫자, 출처, 기준 시점은 코드가 넣어요.
2. 다듬기는 선택입니다(qwen3:4b 채택률 5/7, B 측정). B의 `check_sentences()` 가드와 A의 `numbers_ok()` 가드를 **둘 다 통과**해야 채택합니다. 통과하지 못하면 코드 문장을 그대로 씁니다.
3. 반드시 들어가는 문장은 이래요.
   - "이 지표는 질문에 맞춰 자동으로 구성했습니다(허브 n번 + m번, 결합 기준 …)."
   - 보류나 제외가 있으면 그 사유
   - 기간을 기본값으로 정했다면 그 사실
4. B의 `BANNED` 표현("차려도 된다", "추천합니다" 등)은 G 경로에도 똑같이 금지합니다.

### 7.9 G8 화면 (`app.py`의 `show_graph_result(s)`, B 부품만 사용)

순서는 이래요.

1. `section(f"데이터로 본 답 · {지역} {주제}")`
2. **결론 한 줄**: `jj-note` 스타일, 코드 문장 1번
3. **KPI 4칸**: B의 `kpi()`. 대상 값, 제주 중앙값, 순위/비교 수, 기준 시점
4. **지표 카드**: B의 `indicator_card()`. G 지표 1~3개
5. **근거 그래프 탭**: 제주 안에서의 위치(`position_chart`), 그리고 trend가 있으면 월별 추이, share가 있으면 구성비. plotly이고 B 색(대상 `#0081A7`, 비교 `#DD6418`)을 씁니다.
6. **판단 과정**: B의 `show_log()` 확장. 해석 → 후보 선별(채택과 제외 사유) → 계획(템플릿/LLM) → 검증(통과·수정·보류) → 계산
7. ★**이 답변의 데이터 지도**: `data_map.show_answer(used, places, candidates=rejected)`
8. **보류일 때**: 3~5번 대신 "계산하지 않은 이유"와 "필요한 자료"를 보여줍니다. 추가 자료 요청은 B의 `_unanswered` 기록과 운영자 탭 기록으로 남깁니다.
9. **반출 점검**: B의 기존 `show_export()`

### 7.10 반출 점검 연동 (`policy/export_rules.yaml`)

G 경로 자료는 `code = hub{id}`라서 기존 규칙에 없습니다. 기본 규칙을 추가합니다.

```yaml
graph_default:
  restricted_if_title_matches: "카드|매출|POS|유동인구|통신|와이파이|내비|결제"
  restricted: {group: restricted, center_equivalent: "센터 제한 데이터군과 같은 성격(자동 분류)"}
  otherwise:  {group: open_assumed, note: "허브 공개 데이터 — 운영자 확인 필요"}
```

`tools/export_check.py`는 code가 `hub`로 시작하면 위 규칙으로 분류합니다. `open_assumed`는 운영자 화면에 "자동 분류"로 표시해서 운영자가 최종 판단하게 합니다.

### 7.11 G 경로 반환 구조 (`graph/pipeline.py`)

```python
@dataclass
class GraphResult:
    status: Literal["answered", "partial", "held", "ask"]
    ask: str | None                 # 되묻기 문구(지명 모호 등)
    slots: dict                     # G1 결과(가드 적용 후)
    candidates: list[dict]          # G2 채택(허브ID·제목·접근·기간·점수)
    rejected: dict[int, str]        # G2 제외 {허브ID: 사유} → 지도 회색 노드
    plan: dict | None               # G3
    plan_by: Literal["template", "llm", "none"]
    validation: list[str]           # G4 오류(재계획 전·후)
    results: dict[str, IndicatorResult]
    rows: list[dict]                # judge.table 결과
    sentences: list[str]
    places: list[str]
    steps: list[dict]               # B _step 형식 로그
```

---

## 8. 수정·추가 파일 목록 (B 레포 기준)

| 파일 | 변경 | 단계 |
|---|---|---|
| `tools/data_map.py`, `scripts/build_data_map.py`, `tools/vendor/*`, `data/data_map.json` | 추가(완료) | P0 |
| `app.py` | import, 진단 결과 지도 섹션(완료) / `next_stage`에 `graph` 추가, `show_graph_result()` | P0 |
| `agent/state_machine.py` | `Session.graph_result`, `Session.graph()`, §5.1 라우팅 | P0 |
| `agent/schemas.py` | `GraphSlots`, `GraphPlan` | P0 |
| `agent/prompts/graph_interpret.md` | 추가 | P0 |
| `agent/prompts/graph_plan.md` | 추가 | P1 |
| `graph/*` | §7.0 전체 | P0(interpret, search, plan의 T1·T2·T4, validate, access(API), execute, to_indicator, narrate, pipeline) / P1(나머지) |
| `data/kg.sqlite` | A에서 복사 | P0 |
| `indicators/changup.yaml`, `tools/report.py`, `tools/templates/report.html.j2` | visitPop 단위 표기, I7 처리(§5.0 결과에 따라) | P0 |
| `policy/export_rules.yaml`, `tools/export_check.py` | `graph_default` | P1 |
| `tests/test_graph_*.py` | §9.2 | P0(최소) |
| `eval/run_graph_eval.py`, `eval/graph_questions.jsonl` | §9.3 | P0 |
| `README.md`, 기획서 | §10 | P0 |

**A 레포에서 할 것**: `verified_overrides.json` 결정을 반영하고(§5.0), 그래프를 재생성하고, 이 문서를 `docs/`에 링크합니다. A의 `서비스/`와 `mvp/` 이전 MVP 코드는 더 이상 쓰지 않는다고 README에 표시합니다.

---

## 9. 테스트와 평가

### 9.1 회귀 (기존 B를 깨뜨리지 않는지)

```
.venv\Scripts\python -m pytest -q tests
.venv\Scripts\python -m eval.run_qa50 eval\qa50_after_merge.json
```

- 기준: **QA50 양호 41 이상, 오답 0**이 유지돼야 합니다. 모델을 qwen3:4b로 바꾸면 B의 기존 결과도 다시 재야 합니다(B 측정에서 qwen3:4b 조건 추출 93%).

### 9.2 단위 테스트 (최소)

| 테스트 | 확인 내용 |
|---|---|
| `test_graph_route` | §5.1 표의 각 줄이 기대한 stage로 가는지 확인. 예: "주식 추천" → 안내, "노형동 편의점 몇 개" → graph |
| `test_graph_interpret_guards` | 날짜 없는 질문의 period 제거, 업종 별칭 필터 보정, ratio 자동 채움 |
| `test_graph_search` | 애월 카페 질문에서 793과 583이 채택되고, 746은 793과 결합할 수 없어서(기간 불일치) 제외 사유와 함께 `rejected`에 들어가는지 |
| `test_graph_validate` | 583 visitPop을 sum으로 계획하면 차단, 746 매장수를 분모로 쓰면 차단 |
| `test_graph_execute_offline` | A의 `test_agent_offline.py` 기대값 재현: 애월 228, 한림 152, 1만당 8.32, 11.41 |
| `test_graph_to_indicator` | direction=none이라 판정이 높음·보통·낮음 중 하나인지 |
| `test_data_map` | `answer_graph([793,583,746])`에 결합 선 2개, 746–793 선 없음 |

### 9.3 G 경로 평가 (`eval/run_graph_eval.py`)

**데모 질문(P0 통과 필수)**

| # | 질문 | 기대 |
|---|---|---|
| 1 | 애월에 카페 너무 많을까요? 한림보다 경쟁이 심한지 궁금해요. | 현재 B 창업 검증 경로로 가요. G 경로를 강제로 실행하면 8.32 / 11.41(교차 검증) |
| 2 | 2026년 8월 노형동과 연동의 내국인 방문지표 비교 | 230,606.48 / 246,548.48(A 기대값), 판정 높음·보통·낮음 |
| 3 | 한림읍 편의점은 몇 개야? | 59개(A 기대값). B 업종 목록에도 편의점이 있으니 라우팅을 확인할 것 |

**A의 10문항 전체(P1)**: A의 `mvp/test_questions.py` 질문과 기대값을 그대로 씁니다. 기록할 항목은 이래요.
- 해석 정확도: concepts, places, filters, analysis 각각
- 후보 선별 정확도: 기대 자료가 채택됐는지
- 계획 방식(템플릿/LLM)과 검증 통과율
- 계산 일치
- 응답 시간: 개발 PC와 센터 흉내(§4.4)

**합격 기준(P1)**

| 항목 | 기준 |
|---|---|
| 해석: 기대 개념 포함 | 8/10 이상 |
| 계산 일치(계산 기대 문항) | 전부 일치하거나, 정직하게 보류 |
| 오답(틀린 숫자 출력) | **0** |
| 응답 시간 중앙값(개발 PC) | 30초 이하 |
| 응답 시간 중앙값(센터 흉내) | 측정해서 기획서에 기재 |

결과는 `eval/GRAPH_RESULTS.md`에 B의 `QA50_정확도.md` 형식으로 적습니다.

---

## 10. 기획서 반영 문구

- **구조**: "B(분석관)의 질문 해석·판정·리포트·반출 흐름에 A(지식 그래프)의 데이터 선별을 결합했다. 정해진 창업 검증 질문은 검증된 지표 12종으로, 그 밖의 질문은 지식 그래프가 허브 1,259종 중 필요한 자료와 결합 가능한 조합을 골라 같은 판정 틀로 답한다."
- **범위(D9)**: "지식 그래프는 허브 1,259종 전체를 **탐색**한다. 운영 시에는 센터 서버가 허브 데이터를 보유한다고 가정하며, 이번 데모는 API로 받을 수 있는 자료와 미리 내려받은 자료로 계산을 시연한다." 데모 범위 밖 자료는 "운영 시 계산"으로 표시합니다.
- **모델(D4)**: "운영 중 LLM은 센터 PC에서 Ollama로 돌리는 Qwen3-4B(폴백 Kanana-1.5-2.1B)만 사용한다. 외부 API(GPT-5 mini)는 지식 그래프를 처음 구축할 때 한 번만 사용했다(입력 약 805만 토큰, 출력 약 135만 토큰)." 대회 규정상 사용 모델과 외부 API는 명시해야 합니다.
- **자율 범위**: "에이전트는 자료·컬럼·집계 방법·기간 기본값을 스스로 정하고, 검증에 실패하면 한 번 다시 계획한다. 지명이 모호하면 되묻는다. 검증되지 않은 숫자 출력, 결합할 수 없는 자료 합치기, 관측 자료로 미래 예측, 자동 지표에 유리·불리 판정 붙이기는 하지 않는다."
- **센터 PC 탑재**: VRAM 3GB에서는 qwen3:4b(약 3.2GB)가 일부 CPU로 넘어간다는 점과 측정한 응답 시간을 적고, kanana 2.1B 폴백(VRAM 약 2.0GB)도 적습니다.
- **교차 검증**: 애월 카페 8.32가 독립된 두 구현에서 일치했다는 점.
- **한계**: 그래프 결합 관계 25,461개 중 검증된 것은 14개이고 나머지는 '잠정'입니다(화면에도 잠정 표시). GPT가 제안한 개념 807개는 검수 전이라 해석에 쓰지 않습니다. 파일 자료는 미리보기 기준 컬럼입니다.
- **오픈소스 추가**: vis-network 9.1.13(MIT/Apache-2.0), Qwen3-4B(Apache 2.0).

---

## 11. 위험과 대응

| 위험 | 가능성 | 대응 |
|---|---|---|
| qwen3:4b가 개념 enum을 잘못 고름 | 중 | 코드 가드 3~5번(동의어·업종 사전·ratio 보정). 평가로 정확도 측정 |
| G3 LLM 계획 JSON 오류 | 중 | 템플릿 우선(D7), 1회 재계획, 보류. P0는 템플릿만 |
| 센터 PC에서 느림(일부 CPU 실행) | 중 | kanana 폴백, LLM 호출 수 최소화(G1 1회 + 필요할 때만 G3) |
| 43개 동 전체 API 호출로 쿼터 소진 | 중 | B 캐시 재사용, 데모 질문 결과를 미리 캐시해 둠, 900회 상한 |
| 그래프 '잠정' 결합으로 잘못된 비율 | 중 | 비율은 같은 공간 단위와 겹치는 기간이 있어야 하고, 화면에 '잠정' 표시. 데모는 검증된 쌍(583–793)으로 시연 |
| 746 매장수 판정에 따라 B의 I7을 바꿔야 함 | **높음** | §5.0 검증 코드를 오늘 실행 |
| B의 기존 경로 회귀 | 낮음 | D8: 진입 조건 밖은 건드리지 않음. QA50 재실행 |
| Streamlit 버전 차이(iframe API) | 낮음 | `st.iframe`/`components.html` 자동 선택(구현 완료) |
| `data_map.json`/`kg.sqlite` 용량과 대회 규정 | 낮음 | 참가자 목록 번호 열은 이미 제거된 파일. 원자료는 넣지 않음 |

---

## 12. 마감 이후 로드맵 (P2)

1. **법정동 → 행정동 매핑 통일**: A의 비중 방식(MAPS_TO 81)을 채택하면, B가 확인 불가로 처리한 행정동 9곳(동홍동, 송산동, 정방동, 중앙동, 천지동, 서홍동, 영천동, 이도2동, 아라동)의 카드 지표를 살릴 수 있습니다.
2. **허브 클라이언트 통일**: A의 `data_access.py`를 폐기하고 B의 `hub/client.py`로 일원화합니다.
3. **B의 지표 I1~I12를 그래프 개념과 연결**: 지표마다 MEASURES 경로를 기록해서 "이 지표가 어떤 자료의 어떤 컬럼을 쓰는지"를 데이터 지도로 설명합니다.
4. **개념 807개 검수**: 해석 어휘를 162개에서 늘립니다. 단, 프롬프트 길이 예산(§7.4)을 다시 계산해야 합니다.
5. **창업 외 주제 확장**: 관광, 교통 등을 B의 지표 템플릿 방식으로 늘리고, 후보 탐색은 그래프가 맡습니다.
6. `center_db` 어댑터: 센터 보유 70종을 연결합니다.

---

## 부록 A. 코드 위치 참조

| 기능 | A | B |
|---|---|---|
| 질문 해석 | `mvp/agent.py` `SLOT_SYS`, `interpret()` | `agent/prompts/extract_slots.md`, `agent/steps.py` `extract_slots()` |
| 지명 | `kg_query.KG.place()`, `agent.resolve_place()` | `steps.normalize_region()`, `fuzzy_hits()`, `data/regions.yaml` |
| 업종 | 개념 어휘 '업종' 구분값 | `data/industries.yaml`, `steps.match_industry()` |
| 그래프 탐색 | `kg_query.KG.find_datasets()`, `joinable()`, `plan_pairs()` | — |
| 계획·검증 | `agent.py` `PLAN_SYS`, `validate()` | `steps.pick_indicators()`(지표 선택) |
| 조회 | `mvp/data_access.py` `hub_fetch()`, `file_fetch()` | `hub/client.py` `fetch()`, `data/hub_data.db` |
| 계산 | `agent.aggregate()` | `tools/area_indicators.py` `compute()`, `IndicatorResult` |
| 판정 | — | `tools/judge.py` `table()`, `tools/rank_areas.py` |
| 숫자 가드 | `agent.numbers_ok()` | `report.check_sentences()`, `tools/provenance.py` |
| 화면 | `서비스/app.py`, `app.js`(더 이상 사용 안 함) | `app.py`(Streamlit), `tools/theme.py` |
| LLM 호출 | `mvp/llm_client.py`(OpenAI 호환) | `agent/llm.py`(Ollama, 스키마 강제, pydantic 재검증, 측정 로그) |

## 부록 B. 이번 검토에서 잰 값

| 항목 | 값 |
|---|---|
| 그래프 규모 | 자료 1,259 · 컬럼 7,063 · 개념 969(검수 162) · 지명 120 · 결합 25,461(검증 14) |
| 자료 제공 방식 | API 93(API+파일 20 포함) · 파일 670 · 링크 517 |
| 검수 어휘 162개 이름 길이 | 1,051자 |
| 축소 전 카드 길이 | 583: 1,083자 · 793: 1,727자 · 746: 1,528자 |
| `data_map.json` | 917KB(자료 1,259, B 자료 간 결합 40) |
| qwen3:4b(B 측정) | VRAM 약 3.2GB, 조건 추출(처음 보는 15문항) 93%, 다듬기 채택 5/7 |
| kanana 2.1B(B 측정) | VRAM 약 2.0GB, 전체 약 11초, 다듬기 채택 0/7 |
