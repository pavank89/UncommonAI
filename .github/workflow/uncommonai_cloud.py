import os, json, re, urllib.request
from pathlib import Path
import feedparser

# GitHub Actions runs from the repository root. Keep workspace at:
# <repo>/workspace, not <repo>/.github/workflow/workspace.
ROOT = Path.cwd()
WORK = ROOT / "workspace"
WORK.mkdir(parents=True, exist_ok=True)

MODE = os.getenv("UNCOMMONAI_MODE", "research").lower()
APPROVED_TOPIC = os.getenv("APPROVED_TOPIC", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

FEEDS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
}

# These phrases are deliberately designed to turn technical source headlines
# into viewer-first YouTube concepts rather than copying the source headline.
ANGLE_RULES = [
    (["robot", "robotics", "lerobot", "physical ai"],
     "AI Agents Are Starting to Teach Robots — Here's Why It Matters"),
    (["agent", "agents", "computer use"],
     "AI Agents Are Becoming Useful — Here's What Changed"),
    (["reasoning", "reasoning model"],
     "AI Models Are Getting Better at Thinking — But There's a Catch"),
    (["image", "video generation", "video model"],
     "AI Can Now Create This — And It Changes What Creators Can Do"),
    (["coding", "developer", "code"],
     "AI Is Changing How Software Gets Built — Here's the Part Most People Miss"),
    (["chip", "gpu", "accelerator"],
     "The AI Hardware Race Is Changing — Here's What It Means"),
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
        "agent", "ai", "model", "openai", "google", "coding", "robot",
        "robotics", "computer use", "reasoning", "image", "video",
        "developer", "automation", "chip", "gpu", "physical ai"
    ]
    score = sum(2 if k in r["title"].lower() else 1 for k in keywords if k in text)

    # Prefer stories that have a concrete change, product, demo, or workflow.
    for k in ["launch", "release", "new", "demo", "open source", "available",
              "integration", "update", "announces"]:
        if k in text:
            score += 2
    return score

def youtube_angle(source_title, summary):
    text = (source_title + " " + summary).lower()
    for keywords, angle in ANGLE_RULES:
        if any(k in text for k in keywords):
            return angle

    # Generic fallback: still avoids copying the source title.
    clean = re.sub(r"\s+", " ", source_title).strip()
    return f"What This New AI Development Actually Means for You"

def create_issue(title, body, labels=None):
    return gh_api(f"/repos/{repo()}/issues", "POST", {
        "title": title,
        "body": body,
        "labels": labels or []
    })

def list_open_issues():
    return gh_api(f"/repos/{repo()}/issues?state=open&per_page=30")

def open_issue_with_marker(marker):
    for i in list_open_issues():
        if marker in i.get("body", ""):
            return i
    return None

def research():
    rows = collect_news()
    if not rows:
        raise SystemExit("No research signals found.")

    ranked = sorted(rows, key=score_item, reverse=True)[:12]

    lines = [
        "# uncommonAI Research",
        "",
        "The list below separates the original source headline from the "
        "viewer-first YouTube angle.",
        "",
    ]

    for i, r in enumerate(ranked, 1):
        lines += [
            f"## {i}. {youtube_angle(r['title'], r['summary'])}",
            f"- Original source headline: {r['title']}",
            f"- Source: {r['source']}",
            f"- Published: {r['published']}",
            f"- URL: {r['url']}",
            f"- Evidence/context: {r['summary']}",
            f"- Research score: {score_item(r)}",
            "",
        ]

    (WORK / "research.md").write_text("\n".join(lines), encoding="utf-8")

    top = ranked[0]
    angle = youtube_angle(top["title"], top["summary"])
    marker = "<!-- uncommonai-topic-approval -->"

    body = f"""# uncommonAI topic approval

{marker}

## Recommended YouTube concept

**{angle}**

### Why this is interesting
{top["summary"]}

### Original source
**{top["title"]}**

Source: {top["url"]}

### Editorial rule
This concept is intentionally written for a viewer, not copied from the
source headline. The production stage must independently verify factual
claims and cite the original source.

### Approval
Comment **APPROVE** to start production.

Comment **REJECT** to discard this idea.

The workflow will not publish anything from this approval step.
"""

    existing = open_issue_with_marker(marker)
    if existing:
        print("Existing approval issue:", existing["html_url"])
    else:
        issue = create_issue(
            "🎬 uncommonAI — approve next video topic",
            body,
            ["uncommonai:topic"]
        )
        print("Approval issue:", issue["html_url"])

def gemini_generate(prompt):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "GEMINI_API_KEY is required for production. "
            "Research mode does not require it."
        )

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model
        + ":generateContent?key="
        + api_key
    )

    def request_gemini(instruction):
        payload = json.dumps({
            "contents": [{"parts": [{"text": instruction}]}],
            "generationConfig": {
                "temperature": 0.4,
                "responseMimeType": "application/json",
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            raise SystemExit(f"Gemini API request failed: {exc}")

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise SystemExit(
                f"Unexpected Gemini response: {json.dumps(data)[:2000]}"
            )

    def parse_json(raw):
        raw = raw.strip()

        raw = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()

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
    except json.JSONDecodeError as first_error:
        print("Gemini returned malformed JSON.")
        print("Attempting one JSON repair retry...")

        repair_prompt = f"""
Convert the following malformed JSON into valid JSON.

STRICT RULES:
- Return ONLY valid JSON.
- Use double quotes around every object key.
- Preserve the original content and meaning.
- Do not summarize.
- Do not remove fields.
- Do not add fields.
- Do not add markdown fences.
- Ensure strings are properly escaped.
- Ensure arrays and objects are properly closed.

Malformed JSON:
{raw}
"""

        repaired = request_gemini(repair_prompt)

        try:
            result = parse_json(repaired)
            print("Gemini JSON repair succeeded.")
            return result
        except json.JSONDecodeError as second_error:
            raise SystemExit(
                "Gemini returned invalid JSON after repair retry.\n"
                f"Original error: {first_error}\n"
                f"Repair error: {second_error}\n"
                f"Response:\n{raw[:5000]}"
            )


def build_package(topic):
    prompt = f"""
You are the lead producer for the faceless YouTube channel uncommonAI.

GOAL:
Create a high-retention, original, evidence-aware AI/technology video that
feels like a human editorial product, not an automated news slideshow.

Audience:
Curious professionals, creators and tech enthusiasts who want to understand
important AI developments without needing an engineering background.

APPROVED TOPIC:
{topic}

Create one ORIGINAL 7-10 minute YouTube package specifically about the
approved topic.

EDITORIAL QUALITY:
- Open with a concrete tension, surprising implication, or question in the
  first 10-15 seconds.
- Avoid "In today's video", "Let's dive in", and generic AI-news openings.
- Build a clear narrative: hook -> context -> evidence -> what changed ->
  implications -> limitations -> practical takeaway.
- Prefer concrete examples and mechanisms over hype.
- Clearly distinguish verified facts from interpretation.
- Never invent statistics, quotes, benchmarks, product capabilities or demos.
- Do not copy source headlines or another creator's framing.
- Use original commentary throughout.
- End with one memorable conclusion and a reason to watch the next video.

LONG-FORM VISUAL DESIGN:
Create exactly 8 scenes. Each scene must have:
- "narration": the spoken narration for that scene
- "visual_prompt": a concise description of what an eventual visual should show
- "key_phrase": 3-8 words that can be displayed prominently on screen
- "visual_type": one of: "hook", "comparison", "process", "timeline",
  "evidence", "warning", "takeaway"

SHORTS:
Create exactly 3 Shorts from different parts of the same story.
Each Short must:
- be 25-55 seconds;
- have a different hook and angle;
- deliver one self-contained insight;
- avoid simply summarizing the long video;
- have a title/hook that creates curiosity without clickbait;
- end with a useful conclusion;
- be suitable for vertical 9:16;
- contain no unsupported claims.

SOURCE QUALITY:
- Include the original source URLs in "sources".
- Use sources relevant to the approved topic.
- Do not fabricate URLs.

Return valid JSON only.

Schema:
{{
  "title": "...",
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

    scenes = package.get("scenes", [])
    shorts = package.get("shorts", [])

    if len(scenes) != 8:
        raise SystemExit(f"Expected 8 scenes, found {len(scenes)}")

    if len(shorts) != 3:
        raise SystemExit(f"Expected 3 Shorts, found {len(shorts)}")

    for i, scene in enumerate(scenes, 1):
        if not safe_text(scene.get("narration")):
            raise SystemExit(f"Scene {i} has no narration.")
        if not safe_text(scene.get("key_phrase")):
            raise SystemExit(f"Scene {i} has no key_phrase.")
        if scene.get("visual_type") not in {
            "hook", "comparison", "process", "timeline",
            "evidence", "warning", "takeaway"
        }:
            raise SystemExit(f"Scene {i} has invalid visual_type.")

    for i, short in enumerate(shorts, 1):
        if not safe_text(short.get("title")):
            raise SystemExit(f"Short {i} has no title.")
        if not safe_text(short.get("script")):
            raise SystemExit(f"Short {i} has no script.")

    (WORK / "production_package.json").write_text(
        json.dumps(package, indent=2), encoding="utf-8"
    )
    # Keep the older package filename too for compatibility with any tooling
    # that still expects it.
    (WORK / "package.json").write_text(
        json.dumps(package, indent=2), encoding="utf-8"
    )

    return package


def quality_gate(package):
    # The quality gate uses the same Gemini credential as production.
    prompt = f"""
Act as an extremely strict YouTube editorial and YPP-quality reviewer.

APPROVED TOPIC:
{APPROVED_TOPIC}

Review this generated package:
{json.dumps(package, indent=2)}

Judge ONLY against the approved topic and the actual package.

Return JSON only:
{{
  "pass": true,
  "originality": 0,
  "viewer_value": 0,
  "evidence_quality": 0,
  "repetition_risk": 0,
  "copyright_risk": 0,
  "ypp_risk": 0,
  "title_quality": 0,
  "hook_quality": 0,
  "fixes": []
}}

Fail if the package:
- mainly rewrites another creator/source;
- is generic mass-produced filler;
- contains unsupported factual claims;
- lacks meaningful original explanation or commentary;
- uses repetitive templates with little viewer value;
- has high copyright or YPP risk;
- does not actually address the approved topic.

Also verify:
- major factual claims have appropriate evidence;
- the title matches the actual video;
- the opening hook is specific and useful;
- the 3 Shorts have genuinely different hooks/angles;
- no fabricated statistics, quotes, benchmarks or capabilities appear.
"""
    gate = gemini_generate(prompt)

    (WORK / "quality_gate.json").write_text(
        json.dumps(gate, indent=2), encoding="utf-8"
    )
    return gate


def produce():
    if not APPROVED_TOPIC:
        raise SystemExit("APPROVED_TOPIC is missing.")

    package = build_package(APPROVED_TOPIC)
    gate = quality_gate(package)

    # Advisory during the V5 Shorts rollout.
    # Keep the gate result in workspace/quality_gate.json, but do not stop
    # production while we validate the end-to-end long-video + Shorts pipeline.
    if gate.get("pass"):
        print("QUALITY GATE: PASS")
    else:
        print("QUALITY GATE: WARNING - package did not pass the advisory gate.")
        print("Continuing with production so the generated package can be reviewed.")
    print("Title:", package.get("title"))
    print("Scenes:", len(package.get("scenes", [])))
    print("Shorts:", len(package.get("shorts", [])))
    print("Production package:", WORK / "production_package.json")

if __name__ == "__main__":
    if MODE == "research":
        research()
    elif MODE == "produce":
        produce()
    else:
        raise SystemExit("UNCOMMONAI_MODE must be research or produce.")
