import os, json, re, urllib.request
from pathlib import Path
import feedparser

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "workspace"
WORK.mkdir(exist_ok=True)

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

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
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
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise SystemExit(f"Unexpected Gemini response: {json.dumps(data)[:2000]}")

    text = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.I)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Gemini returned invalid JSON: {exc}\n{text[:3000]}")


def build_package(topic):
    prompt = f"""
You are the lead producer for the faceless YouTube channel uncommonAI.

Audience:
Curious professionals, creators and tech enthusiasts who want to understand
important AI developments without needing an engineering background.

APPROVED TOPIC:
{topic}

Create one ORIGINAL 7-10 minute YouTube package specifically about the
approved topic.

CRITICAL TOPIC RULES:
- Stay faithful to the approved topic.
- Do not reuse a previous video's topic, products, examples or framing unless
  genuinely relevant.
- Never substitute the topic with "5 AI tools" or another hard-coded concept.
- If the topic is a list, use the appropriate items for THIS topic.
- If the topic is about one subject, stay focused on that subject.

CONTENT RULES:
- Hook viewers in the first 15 seconds.
- Explain why the topic matters.
- Use simple language before technical detail.
- Never invent statistics, quotes, benchmarks, demonstrations or capabilities.
- Separate verified facts from interpretation.
- Include source URLs in the sources array.
- Avoid generic AI-news roundup structure.
- Give the viewer a clear takeaway.
- Create exactly 8 visual scenes.
- Create exactly 3 Shorts derived from the same story, each with a different
  hook, angle and takeaway.
- Shorts should be suitable for vertical 9:16 video and approximately
  30-55 seconds each.
- Return valid JSON only.

Schema:
{{
  "title": "...",
  "description": "...",
  "tags": ["..."],
  "thumbnail_prompt": "...",
  "script": "...",
  "scenes": [
    {{"narration":"...", "visual_prompt":"..."}}
  ],
  "shorts": [
    {{
      "title":"...",
      "script":"...",
      "visual_prompt":"..."
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

    if not gate.get("pass"):
        raise SystemExit(
            "Quality gate failed. See workspace/quality_gate.json."
        )

    print("QUALITY GATE: PASS")
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
