#!/usr/bin/env python3
import os
import json
import re
import urllib.request
from pathlib import Path
import feedparser

# GitHub Actions runs from the repository root. Isolated workspace for parallel testing.
ROOT = Path.cwd()
WORK = ROOT / "workspace_v2"
WORK.mkdir(parents=True, exist_ok=True)

MODE = os.getenv("UNCOMMONAI_MODE", "research").lower()
APPROVED_TOPIC = os.getenv("APPROVED_TOPIC", "").strip()

def safe_text(value):
    """Normalize text safely for validation and display."""
    return re.sub(r"\s+", " ", str(value or "")).strip()

FEEDS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
}

ANGLE_RULES = [
    ([
        "agent",
        "agents",
        "computer use",
        "mcp",
        "model context protocol",
    ], "Why AI Agents and MCP Servers Break Production Pipelines"),
    ([
        "test",
        "testing",
        "evaluation",
        "llm-as-a-judge",
        "benchmark",
    ], "The Hidden Flaws in AI Test Validation Everyone Ignores"),
    ([
        "robot",
        "robotics",
        "lerobot",
        "physical ai",
    ], "AI Agents Are Training Robots — Here's Why Production Fails"),
]

def gh_api(path, method="GET", body=None):
    token = os.environ["GITHUB_TOKEN"]
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        "https://api.github.com" + path, data=data, method=method
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def repo():
    return os.environ["GITHUB_REPOSITORY"]

def collect_news():
    rows = []
    for source, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:10]:
                title = e.get("title", "").strip()
                summary = re.sub("<[^>]+>", " ", e.get("summary", ""))
                summary = re.sub(r"\s+", " ", summary).strip()
                rows.append({
                    "source": source,
                    "title": title,
                    "url": e.get("link", ""),
                    "published": e.get("published", ""),
                    "summary": summary[:900],
                })
        except Exception as exc:
            print("Feed error:", source, exc)
    return rows

def score_item(r):
    text = (r["title"] + " " + r["summary"]).lower()
    keywords = [
        "agent", "ai", "model", "mcp", "testing", "evaluation",
        "pipeline", "ci/cd", "security", "developer", "automation"
    ]
    score = sum(3 if k in r["title"].lower() else 1 for k in keywords if k in text)
    for k in ["launch", "release", "failure", "risk", "breaking", "critical", "vulnerability"]:
        if k in text:
            score += 2
    return score

def youtube_angle(source_title, summary):
    text = (source_title + " " + summary).lower()
    for keywords, angle in ANGLE_RULES:
        if any(k in text for k in keywords):
            return angle
    return "Why This New Engineering Bottleneck Changes Everything"

def gemini_generate(prompt):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required for production.")

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    def request_gemini(instruction):
        payload = json.dumps({
            "contents": [{"parts": [{"text": instruction}]}],
            "generationConfig": {
                "temperature": 0.4,
                "responseMimeType": "application/json",
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def parse_json(raw):
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start:end + 1])
            raise

    raw = request_gemini(prompt)
    try:
        return parse_json(raw)
    except json.JSONDecodeError:
        repair_prompt = f"Convert the following malformed JSON into valid JSON with double quotes. Return ONLY valid JSON:\n{raw}"
        repaired = request_gemini(repair_prompt)
        return parse_json(repaired)

def build_package(topic):
    prompt = f"""
You are the principal architecture reviewer and senior producer for the technical engineering channel uncommonAI.
Create one original 7-10 minute long-form YouTube video package and 3 distinct short-form packages based on this challenge:

APPROVED TOPIC / TECHNICAL CHALLENGE:
{topic}

==================== VISUALS (8 SCENES) ====================
Create exactly 8 scenes. Every scene requires:
- narration: punchy, authoritative, professional tone.
- visual_prompt: precise technical diagram concept.
- key_phrase: 3-8 words for on-screen focus.
- visual_type: exactly one of: hook, comparison, process, timeline, evidence, warning, takeaway.

==================== SHORTS (3 DISTINCT SHORTS) ====================
Create 3 high-velocity Shorts (25-55 seconds each) designed to maximize audience retention.

==================== JSON OUTPUT ====================
Return VALID JSON ONLY. No markdown fences. Schema:
{{
  "title": "...",
  "chosen_title": "...",
  "thumbnail_text": "...",
  "description": "...",
  "tags": ["..."],
  "thumbnail_prompt": "...",
  "script": "...",
  "scenes": [
    {{
      "narration": "...",
      "visual_prompt": "...",
      "key_phrase": "...",
      "visual_type": "hook"
    }}
  ],
  "shorts": [
    {{
      "title": "...",
      "hook": "...",
      "script": "...",
      "visual_prompt": "..."
    }}
  ],
  "sources": ["https://..."]
}}
"""
    package = gemini_generate(prompt)
    if not isinstance(package, dict):
        raise SystemExit("Gemini production response is not a JSON object.")

    title = safe_text(package.get("title") or package.get("chosen_title"))
    package["title"] = title
    package["chosen_title"] = title

    (WORK / "production_package.json").write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")
    return package

def produce():
    if not APPROVED_TOPIC:
        raise SystemExit("APPROVED_TOPIC is missing.")
    package = build_package(APPROVED_TOPIC)
    print("Growth-Optimized Production Package Generated Successfully in workspace_v2.")

if __name__ == "__main__":
    if MODE == "produce":
        produce()
    else:
        raise SystemExit("Mode must be produce for this parallel test script.")
