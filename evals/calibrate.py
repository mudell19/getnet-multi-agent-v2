"""Judge calibration (FR-066): export a labeling sheet, then report agreement with human labels.

  uv run python evals/calibrate.py export [--results F] [--sheet F]
  uv run python evals/calibrate.py report --labels FILE [--out F]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = ["case_id", "criterion", "judge_verdict", "human_label", "answer_excerpt"]


def export(results, sheet) -> int:
    rows = []
    for ln in Path(results).read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        c = json.loads(ln)
        excerpt = " ".join((c.get("answer") or "").split())[:300]
        for it in c.get("judge_items", []):
            rows.append([c["id"], it["criterion"], it["verdict"], "", excerpt])
    with open(sheet, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    return len(rows)


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((a.count(k) / n) * (b.count(k) / n) for k in set(a) | set(b))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def report(labels, out) -> tuple[int, float, float]:
    with open(labels, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("human_label") or "").strip()]
    if not rows:
        raise SystemExit("no labeled rows (fill the human_label column with pass/fail)")
    judge = [r["judge_verdict"].strip().lower() for r in rows]
    human = [r["human_label"].strip().lower() for r in rows]
    agree = sum(x == y for x, y in zip(judge, human, strict=True)) / len(rows)
    kappa = cohen_kappa(judge, human)
    dis = [r for r, j, h in zip(rows, judge, human, strict=True) if j != h]
    L = ["# Judge calibration", "", f"- Labeled items: {len(rows)}", f"- Agreement rate: {agree:.3f}",
         f"- Cohen's kappa: {kappa:.3f}", "", "## Disagreements", ""]
    L += [f"- `{r['case_id']}` / {r['criterion']}: judge {r['judge_verdict']}, human {r['human_label']}"
          for r in dis] or ["None."]
    Path(out).write_text("\n".join(L) + "\n", encoding="utf-8")
    return len(rows), agree, kappa


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--results", default=str(HERE / "results.jsonl"))
    e.add_argument("--sheet", default=str(HERE / "labeling_sheet.csv"))
    r = sub.add_parser("report")
    r.add_argument("--labels", required=True)
    r.add_argument("--out", default=str(HERE / "calibration_report.md"))
    a = ap.parse_args(argv)
    if a.cmd == "export":
        print(f"{export(a.results, a.sheet)} rows -> {a.sheet}")
    else:
        n, agree, kappa = report(a.labels, a.out)
        print(f"n={n} agreement={agree:.3f} kappa={kappa:.3f} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
