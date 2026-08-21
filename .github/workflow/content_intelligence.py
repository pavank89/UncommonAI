#!/usr/bin/env python3
"""
uncommonAI Content Intelligence V1

Schema-tolerant scorer for workspace/production_package.json.
No external API is required.

Usage:
    python content_intelligence.py \
        --package workspace/production_package.json \
        --output workspace/content_intelligence.json
"""

import argparse
import json
import re
from pathlib import Path


GENERIC_PHRASES = [
    "in this video",
    "let's dive in",
    "today we are",
    "here is what",
    "here's what",
    "the future of ai",
    "ai is changing",
    "artificial intelligence is changing",
    "everything you need to know",
    "you won't believe",
]

FORMAT_HINTS = {
    "experiment": ["test", "tested", "experiment", "benchmark", "trial", "result"],
    "comparison": ["compare", "versus", "vs", "better than", "winner"],
    "investigation": ["investigate", "investigation", "evidence", "why", "what happened"],
    "explainer": ["how", "explained", "what is", "why does"],
    "case_study": ["case study", "real world", "workflow", "production"],
    "tutorial": ["how to", "step by step", "guide", "build"],
}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def words(text):
    return re.findall(r"\b[\w'-]+\b", clean(text).lower())


def detect_format(title, script, scenes):
    blob = f"{title} {script}".lower()
    scores = {}
    for name, hints in FORMAT_HINTS.items():
        scores[name] = sum(blob.count(h) for h in hints)

    # Scene metadata can override weak title-based detection.
    for scene in scenes:
        value = clean(
            scene.get("format")
            or scene.get("visual_type")
            or scene.get("visual")
        ).lower()
        for name in FORMAT_HINTS:
            if name in value:
                scores[name] += 2

    best = max(scores, key=scores.get)
    return best if scores[best] else "explainer"


def score_package(package):
    title = clean(
        package.get("chosen_title")
        or package.get("title")
    )
    description = clean(package.get("description"))
    script = clean(package.get("script"))
    scenes = package.get("scenes") or []

    full_text = f"{title} {description} {script}"

    # Specificity: named technologies, numbers, tests, products, dates,
    # concrete actions and concrete outcomes are useful signals.
    concrete_terms = re.findall(
        r"\b(?:20\d{2}|[0-9]+%|[0-9]+x|[0-9]+ms|[0-9]+s|"
        r"API|SDK|GPU|CPU|RAG|LLM|QA|SDET|Python|Kubernetes|"
        r"Playwright|Selenium|AWS|Google|OpenAI|Gemini|Claude)\b",
        full_text,
        flags=re.I,
    )
    specificity = min(100, 35 + len(concrete_terms) * 5)

    generic_hits = sum(full_text.lower().count(p) for p in GENERIC_PHRASES)
    generic_penalty = min(40, generic_hits * 6)

    title_words = len(words(title))
    title_score = 100 if 6 <= title_words <= 18 else 70 if title_words else 0

    scene_count = len(scenes)
    scene_score = 100 if scene_count >= 8 else 80 if scene_count >= 6 else 45

    formats = []
    narration_lengths = []
    for scene in scenes:
        fmt = clean(
            scene.get("format")
            or scene.get("visual_type")
            or scene.get("visual")
        )
        formats.append(fmt or "unspecified")
        narration_lengths.append(len(words(scene.get("narration"))))

    unique_formats = len(set(formats))
    format_diversity = min(100, unique_formats * 25)

    repeated_narration = 0
    for a, b in zip(narration_lengths, narration_lengths[1:]):
        if a and b and abs(a - b) <= 3:
            repeated_narration += 1
    repetition_penalty = min(30, repeated_narration * 5)

    originality = max(
        0,
        min(
            100,
            45
            + min(30, specificity * 0.30)
            + min(20, format_diversity * 0.20)
            + min(15, title_score * 0.15)
            - generic_penalty
            - repetition_penalty,
        ),
    )

    detected_format = detect_format(title, script, scenes)

    overall = round(
        originality * 0.35
        + specificity * 0.20
        + title_score * 0.10
        + format_diversity * 0.15
        + scene_score * 0.15
        + (100 - repetition_penalty) * 0.05
    )

    warnings = []

    if generic_hits:
        warnings.append(
            f"Generic/template phrasing detected ({generic_hits} hits)."
        )

    if unique_formats < 2:
        warnings.append(
            "Scenes use little visual-format diversity."
        )

    if scene_count < 6:
        warnings.append(
            f"Only {scene_count} scenes found; expected at least 6."
        )

    if title_words < 6:
        warnings.append(
            "Title may be too short to communicate a specific proposition."
        )

    if repetition_penalty:
        warnings.append(
            "Several adjacent scenes have nearly identical narration lengths."
        )

    return {
        "version": 1,
        "title": title,
        "detected_format": detected_format,
        "scores": {
            "overall": int(round(overall)),
            "originality": int(round(originality)),
            "specificity": int(round(specificity)),
            "format_diversity": int(round(format_diversity)),
            "scene_quality": int(round(scene_score)),
        },
        "signals": {
            "scene_count": scene_count,
            "unique_visual_formats": unique_formats,
            "generic_phrase_hits": generic_hits,
            "repetition_penalty": repetition_penalty,
        },
        "warnings": warnings,
        "decision": "PASS" if overall >= 60 and originality >= 60 else "REVIEW",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    package = json.loads(
        Path(args.package).read_text(encoding="utf-8")
    )
    result = score_package(package)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))

    if result["decision"] == "REVIEW":
        print("CONTENT INTELLIGENCE: REVIEW")
    else:
        print("CONTENT INTELLIGENCE: PASS")


if __name__ == "__main__":
    main()
