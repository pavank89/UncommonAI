#!/usr/bin/env python3
"""
uncommonAI Monetization Safety Gate V1.

This is an internal quality gate, not a guarantee of YouTube monetization.
It looks for obvious signs of repetitive/template production and missing
originality signals.

Usage:
    python monetization_gate.py \
      --package workspace/production_package.json \
      --intelligence workspace/content_intelligence.json
"""

import argparse
import json
import re
from pathlib import Path


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--intelligence", required=True)
    args = parser.parse_args()

    package = json.loads(
        Path(args.package).read_text(encoding="utf-8")
    )
    intelligence = json.loads(
        Path(args.intelligence).read_text(encoding="utf-8")
    )

    title = clean(
        package.get("chosen_title") or package.get("title")
    )
    script = clean(package.get("script"))
    scenes = package.get("scenes") or []

    reasons = []

    if not title:
        reasons.append("Missing title.")

    if len(script.split()) < 250:
        reasons.append("Script is unusually short for a long-form production.")

    if len(scenes) < 6:
        reasons.append("Too few scenes.")

    scores = intelligence.get("scores", {})
    originality = int(scores.get("originality", 0))
    overall = int(scores.get("overall", 0))

    if originality < 60:
        reasons.append(
            f"Originality score {originality} is below the 60-point gate."
        )

    if overall < 60:
        reasons.append(
            f"Overall content score {overall} is below the 60-point gate."
        )

    warnings = intelligence.get("warnings", [])
    for warning in warnings:
        if "visual-format diversity" in warning.lower():
            reasons.append(warning)

    decision = "PASS" if not reasons else "REVIEW"

    result = {
        "version": 1,
        "decision": decision,
        "reasons": reasons,
        "youtube_monetization_guaranteed": False,
        "note": (
            "This gate is an internal production-quality check. "
            "Final YPP eligibility is determined by YouTube."
        ),
    }

    output = Path(args.package).parent / "monetization_gate.json"
    output.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))

    if decision != "PASS":
        raise SystemExit(
            "Monetization/content gate requires REVIEW."
        )


if __name__ == "__main__":
    main()
