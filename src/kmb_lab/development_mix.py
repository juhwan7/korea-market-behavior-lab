from __future__ import annotations

import subprocess
from typing import Iterable

PRODUCT_PREFIXES = (
    "src/kmb_lab/adapters/", "src/kmb_lab/pipeline.py", "src/kmb_lab/flow.py",
    "src/kmb_lab/market_strength.py", "src/kmb_lab/smart_money.py", "data/market/",
    "data/news/", "data/stocks/", "data/config/",
)
MAINTENANCE_PREFIXES = ("docs/", "data/ai/", ".github/workflows/", "web/")


def classify_paths(paths: Iterable[str]) -> str:
    rows = [p.strip() for p in paths if p and p.strip()]
    product = sum(1 for p in rows if p.startswith(PRODUCT_PREFIXES))
    maintenance = sum(1 for p in rows if p.startswith(MAINTENANCE_PREFIXES))
    if product > maintenance:
        return "product"
    if maintenance > product:
        return "maintenance"
    return "unclassified"


def git_development_mix(window_hours: int = 24) -> dict:
    try:
        raw = subprocess.check_output(
            ["git", "log", f"--since={window_hours} hours ago", "--pretty=format:@@%H|%s", "--name-only"],
            text=True,
        )
    except Exception as exc:
        return {"status": "UNKNOWN", "reason": str(exc), "window_hours": window_hours}
    commits = []
    current = None
    for line in raw.splitlines():
        if line.startswith("@@"):
            if current:
                commits.append(current)
            sha, _, subject = line[2:].partition("|")
            current = {"sha": sha, "subject": subject, "paths": []}
        elif current is not None and line.strip():
            current["paths"].append(line.strip())
    if current:
        commits.append(current)
    for row in commits:
        subject = row["subject"].lower()
        if subject.startswith("product:"):
            row["class"] = "product"
        elif subject.startswith("maintenance:"):
            row["class"] = "maintenance"
        else:
            row["class"] = classify_paths(row["paths"])
    labeled = [c for c in commits if c["class"] in {"product", "maintenance"}]
    product_count = sum(c["class"] == "product" for c in labeled)
    pct = round(product_count / len(labeled) * 100, 1) if labeled else None
    return {
        "status": "ESTIMATED" if labeled else "UNKNOWN",
        "method": "commit_path_classification",
        "window_hours": window_hours,
        "target_product_min_pct": 70,
        "product_pct": pct,
        "maintenance_pct": round(100-pct, 1) if pct is not None else None,
        "labeled_commit_count": len(labeled),
        "unclassified_commit_count": len(commits)-len(labeled),
        "warning": bool(pct is not None and pct < 70),
        "recent": [{k: c[k] for k in ("sha", "subject", "class")} for c in commits[:30]],
    }
