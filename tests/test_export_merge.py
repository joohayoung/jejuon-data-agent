"""원문 데이터 반출 신청·운영자 점검·PDF 기록·원문 연결(흐름 5~9). 팀원 jeju-analyst-poc의 시험을 이 앱에 맞춰 옮김."""
import pytest

from tools import admin_report, data_export, export_flow


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(export_flow, "DB", tmp_path / "app.db")
    return export_flow


def _pick(o, form_code, fmt, reason="사유", exc=""):
    forms = list(data_export.FORMS)
    form = forms[list(data_export.FORMS.values()).index(form_code)]
    return data_export.precheck(o, form, fmt, "범위", reason, exc)


def test_options_cover_all_hub_datasets_from_graph():
    by = {o["id"]: o for o in data_export.options()}
    assert len(by) == 1259
    assert by["hub:583"]["group"] == "restricted" and by["hub:793"]["group"] == "open"


def test_data_request_precheck_follows_center_rules():
    by = {o["id"]: o for o in data_export.options()}
    pop, store = by["hub:583"], by["hub:793"]
    assert _pick(pop, "raw", "csv")["사전 판정"] == "불가"          # 제한 데이터군 원본 불가
    assert _pick(pop, "raw", "png")["사전 판정"] == "불가"          # 원본은 형식과 관계없이 불가
    assert _pick(pop, "applied", "csv")["사전 판정"] == "조건부"     # 제한 데이터군 집계 csv는 조건부(예외 사유)
    exc = _pick(pop, "applied", "csv", exc="자체 분석 도구가 csv만 읽음")
    assert exc["예외 필요"] and not any("아직 없습니다" in x for x in exc["사전 이유"])
    assert _pick(pop, "applied", "png")["사전 판정"] == "가능"       # 응용집계 그림 가능
    assert _pick(pop, "simple", "png")["사전 판정"] == "조건부"      # 단순집계 10 미만 범주 처리
    assert _pick(store, "raw", "csv")["사전 판정"] == "가능"         # 개방 데이터군 원본 가능
    assert _pick(pop, "applied", "png", reason="")["사전 판정"] == "조건부"   # 사유 없으면 조건부


def test_request_keeps_question_and_partial_approval(db):
    by = {o["id"]: o for o in data_export.options()}
    items = [_pick(by["hub:583"], "raw", "csv"), _pick(by["hub:583"], "applied", "png"), _pick(by["hub:793"], "raw", "csv")]
    rec = data_export.create(items, "창업 준비 근거", question="연동에 치킨집 하나 차리려는데 경쟁 심한 편이야?", area="연동")
    assert rec["status"] == "대기" and rec["question"].startswith("연동에 치킨집") and [i["locked"] for i in rec["items"]] == [True, False, False]
    choices = {i["file"]: {"approve": True} for i in rec["items"]}
    choices[rec["items"][2]["file"]] = {"approve": False, "reason": ""}
    d = export_flow.decide(rec["id"], choices, "확인")
    assert d["status"] == "부분승인"
    st = data_export.approval_statement(d)
    assert export_flow.DEFAULT_REASON in st and "jejudatahub.net/data/view/data/583" in st
    with pytest.raises(ValueError):
        export_flow.decide(rec["id"], choices)      # 점검은 한 번만 반영


def test_request_id_rejects_path_tricks(db):
    with pytest.raises(ValueError):
        export_flow.load("../../etc/passwd")


def test_deliver_links_to_hub_page():
    r = data_export.deliver({"dataset_id": "hub:583"})
    assert r["mode"] == "link" and r["url"].endswith("/data/view/data/583")
    assert data_export.deliver({"dataset_id": "cat:resident"})["mode"] == "none"


def test_admin_pdf_is_pdf():
    pytest.importorskip("kaleido")
    rec = {"id": "REQ-T", "created_at": "2026-11-19T10:00:00", "status": "승인", "question": "시험", "kind": "data",
           "decided_at": "2026-11-19T11:00:00", "admin_note": "", "items": [
               {"name": "시험 데이터 · 응용집계 · png", "dataset_id": "hub:583", "scope": "-", "사전 판정": "가능",
                "decision": "동의", "exclude_reason": ""}]}
    try:
        pdf = admin_report.build_pdf([rec])
    except RuntimeError as e:          # PDF 엔진(크롬)이 없는 환경
        pytest.skip(str(e))
    assert pdf.startswith(b"%PDF")


def test_project_code_has_no_sample_output():
    from tools import export_check
    assert export_check.scan_code(export_check.project_code_files()) == []


def test_unanswered_log_and_freshness(tmp_path, monkeypatch):
    import datetime as dt
    monkeypatch.setattr(export_flow, "UNANSWERED", tmp_path / "u.jsonl")
    export_flow.log_unanswered("연동 땅값 앞으로 오를까?", "데이터로 답할 수 없는 요구", {"unsupported": "미래 예측"})
    assert export_flow.unanswered()[0]["질문"].startswith("연동 땅값")
    fr = {r["허브 번호"]: r for r in data_export.freshness(dt.date(2026, 11, 19))}
    assert fr[583]["최신 기준일"] == "2026-08-31" and fr[583]["상태"] == "최신"
