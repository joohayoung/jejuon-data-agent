"""반출 규칙 점검 시험(팀원 jeju-analyst-poc tests/test_export.py에서 옮김). 입력 수치는 규칙 확인용 손 계산 값이다."""
from tools.export_check import check_artifact, scan_code, small_value_label

BASE = {"source_text": "출처", "reason": "창업 지원사업 신청서 근거 자료"}


def test_simple_aggregate_with_small_value_is_conditional_and_categorized():
    r = check_artifact({**BASE, "file": "a.png", "agg_type": "simple", "format": "png",
                        "datasets": ["pop_kr"], "simple_values": [12, 9, 30]})
    assert r["판정"] == "조건부"
    assert r["10 미만 값"] == 1
    assert any("범주 처리" in t for t in r["적용 처리"])
    assert [small_value_label(v) for v in [12, 9, 30]] == [12, "10 미만", 30]


def test_simple_aggregate_without_small_value_is_ok():
    r = check_artifact({**BASE, "file": "a.png", "agg_type": "simple", "format": "png",
                        "datasets": ["card_emd"], "simple_values": [10, 25]})
    assert r["판정"] == "가능"


def test_applied_aggregate_is_ok():
    r = check_artifact({**BASE, "file": "t.png", "agg_type": "applied", "format": "png", "datasets": ["card_emd"]})
    assert r["판정"] == "가능"


def test_raw_rows_restricted_forbidden():
    r = check_artifact({**BASE, "file": "rows.png", "agg_type": "raw", "format": "png", "datasets": ["pop_kr"]})
    assert r["판정"] == "불가"


def test_store_name_always_forbidden_even_if_open():
    r = check_artifact({**BASE, "file": "s.png", "agg_type": "applied", "format": "png",
                        "datasets": ["store"], "fields": ["상호명", "점포 수"]})
    assert r["판정"] == "불가"


def test_restricted_csv_forbidden_and_html_conditional():
    assert check_artifact({**BASE, "file": "t.csv", "agg_type": "applied", "datasets": ["card_jeju"]})["판정"] == "불가"
    assert check_artifact({**BASE, "file": "r.html", "agg_type": "applied", "datasets": ["card_jeju"]})["판정"] == "조건부"


def test_missing_reason_is_conditional():
    r = check_artifact({"file": "t.png", "agg_type": "applied", "format": "png", "datasets": ["card_emd"],
                        "source_text": "출처"})
    assert r["판정"] == "조건부"


def test_code_with_head_is_caught(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import pandas as pd\ndf = pd.DataFrame()\nprint(df." + "head())\n", encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    assert len(scan_code([bad])) == 1
    assert scan_code([good]) == []
    assert check_artifact({"file": str(bad), "agg_type": "code"})["판정"] == "불가"
