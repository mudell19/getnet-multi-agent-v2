"""T030: judge calibration (FR-066)."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[2] / "evals"
spec = importlib.util.spec_from_file_location("eval_calibrate", EVALS / "calibrate.py")
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


def test_export_columns(tmp_path):
    res = tmp_path / "results.jsonl"
    res.write_text(json.dumps({"id": "s01", "answer": "Long   answer\ntext", "judge_items": [
        {"criterion": "a", "kind": "must_mention", "verdict": "pass", "rationale": ""},
        {"criterion": "b", "kind": "must_not", "verdict": "fail", "rationale": ""}]}) + "\n"
        + json.dumps({"id": "s02", "answer": "x", "judge_items": []}) + "\n")
    sheet = tmp_path / "sheet.csv"
    assert cal.export(res, sheet) == 2
    rows = list(csv.DictReader(open(sheet)))
    assert list(rows[0]) == ["case_id", "criterion", "judge_verdict", "human_label", "answer_excerpt"]
    assert rows[0]["human_label"] == "" and rows[1]["judge_verdict"] == "fail"
    assert rows[0]["answer_excerpt"] == "Long answer text"


def test_kappa_known_example():
    # 2x2: both pass 20, both fail 15, judge pass/human fail 5, judge fail/human pass 10 -> po=0.7
    j = ["pass"] * 20 + ["fail"] * 15 + ["pass"] * 5 + ["fail"] * 10
    h = ["pass"] * 20 + ["fail"] * 15 + ["fail"] * 5 + ["pass"] * 10
    # pe = (25/50)(30/50) + (25/50)(20/50) = 0.30 + 0.20 = 0.5 -> kappa = 0.4
    assert cal.cohen_kappa(j, h) == pytest.approx(0.4)
    assert cal.cohen_kappa(["pass", "fail"], ["pass", "fail"]) == 1.0
    assert cal.cohen_kappa(["pass", "pass"], ["pass", "pass"]) == 1.0


def test_report_agreement_and_kappa(tmp_path):
    labels = tmp_path / "labels.csv"
    with open(labels, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cal.COLUMNS)
        w.writerows([["a", "c1", "pass", "pass", ""], ["b", "c1", "pass", "fail", ""],
                     ["c", "c1", "fail", "fail", ""], ["d", "c1", "fail", "", ""]])  # last unlabeled
    out = tmp_path / "rep.md"
    n, agree, kappa = cal.report(labels, out)
    assert n == 3 and agree == pytest.approx(2 / 3)
    assert kappa == pytest.approx(0.4)  # po=2/3, pe=(2/3)(1/3)+(1/3)(2/3)=4/9
    text = out.read_text()
    assert "Agreement rate: 0.667" in text and "Cohen's kappa" in text and "`b`" in text
