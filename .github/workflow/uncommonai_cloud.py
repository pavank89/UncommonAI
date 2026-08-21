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

def openai_client():
    if not OPENAI_API_KEY:
        raise SystemExit(
            "OPENAI_API_KEY is required for production. "
            "Research mode does not require it."
        )
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)

def json_response(client, prompt):
    r = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        input=prompt
    )
    text = re.sub(r"^```json\s*|\s*```$", "", r.output_text.strip(), flags=re.I)
    return json.loads(text)

def build_package(topic):
    client = openai_client()
    prompt = f"""
You are the lead producer for the faceless YouTube channel uncommonAI.

Audience:
Curious professionals, creators and tech enthusiasts who want to understand
important AI developments without needing an engineering background.

Approved concept:
{topic}

Create one ORIGINAL 7-10 minute YouTube package.

Rules:
- The concept must be transformed into an engaging story, not a rewrite of a
  source article.
- Hook viewers in the first 15 seconds.
- Explain why the development matters.
- Use simple language before technical detail.
- Never invent statistics, quotes, benchmarks, demonstrations or capabilities.
- Separate verified facts from interpretation.
- Include source URLs in the sources array.
- Avoid generic AI-news roundup structure.
- Give the viewer a clear takeaway.
- Create 8 visual scenes.
- Create 3 Shorts derived from the original story but with different hooks.
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
  {{"title":"...", "script":"...", "visual_prompt":"..."}}
],
"sources": ["https://..."]
}}
"""
    package = json_response(client, prompt)
    (WORK / "package.json").write_text(
        json.dumps(package, indent=2), encoding="utf-8"
    )
    return package

def quality_gate(package):
    client = openai_client()
    prompt = f"""
Act as an extremely strict YouTube editorial and YPP-quality reviewer.

Review:
{json.dumps(package, indent=2)}

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
- has high copyright or YPP risk.
"""
    gate = json_response(client, prompt)
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

    body = f"""# uncommonAI — production ready

<!-- uncommonai-production -->

## {package['title']}

Quality gate: **PASS**

Originality: {gate.get('originality')}
Viewer value: {gate.get('viewer_value')}
Evidence quality: {gate.get('evidence_quality')}
Title quality: {gate.get('title_quality')}
Hook quality: {gate.get('hook_quality')}

The package is stored in the workflow artifact.

### Final approval

Comment **PUBLISH** only after reviewing the generated package.

No YouTube upload occurs from the topic approval.
"""

    issue = create_issue(
        f"🎬 uncommonAI — final approval: {package['title']}",
        body,
        ["uncommonai:ready-to-publish"]
    )
    print("Final approval issue:", issue["html_url"])

if __name__ == "__main__":
    if MODE == "research":
        research()
    elif MODE == "produce":
        produce()
    else:
        raise SystemExit("UNCOMMONAI_MODE must be research or produce.")
