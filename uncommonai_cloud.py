import os, json, re, sys, subprocess, textwrap, urllib.request, urllib.parse, time
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

def gh_api(path, method="GET", body=None):
    token = os.environ["GITHUB_TOKEN"]
    url = "https://api.github.com" + path
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
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
                rows.append({
                    "source": source,
                    "title": e.get("title", ""),
                    "url": e.get("link", ""),
                    "published": e.get("published", ""),
                    "summary": re.sub("<[^>]+>", " ", e.get("summary", ""))[:700],
                })
        except Exception as exc:
            print("Feed error", source, exc)
    return rows

def simple_rank(rows):
    keywords = ["agent", "ai", "model", "openai", "google", "coding", "robot", "computer use",
                "reasoning", "image", "video", "developer", "automation", "chip"]
    scored = []
    for r in rows:
        text = (r["title"] + " " + r["summary"]).lower()
        score = sum(1 for k in keywords if k in text)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1]["published"]))
    return [x[1] for x in scored[:12]]

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
    rows = simple_rank(collect_news())
    if not rows:
        raise SystemExit("No research signals found.")

    lines = ["# uncommonAI Research", "", "## Candidate topics", ""]
    for i, r in enumerate(rows, 1):
        lines += [
            f"### {i}. {r['title']}",
            f"- Source: {r['source']}",
            f"- Published: {r['published']}",
            f"- URL: {r['url']}",
            f"- Signal: {r['summary']}",
            ""
        ]
    text = "\n".join(lines)
    (WORK / "research.md").write_text(text, encoding="utf-8")

    top = rows[0]
    marker = "<!-- uncommonai-topic-approval -->"
    body = f"""# uncommonAI topic approval

{marker}

## Recommended topic
**{top['title']}**

**Why now:** {top['summary']}

**Source:** {top['url']}

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
            "Research mode is free; AI production is not guaranteed free."
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
You are the lead producer for a faceless YouTube channel called uncommonAI.
Audience: curious professionals and creators interested in AI, useful tools,
AI agents, surprising AI experiments and practical workflows.

Create one ORIGINAL video package about:
{topic}

Requirements:
- 7-10 minute video.
- Strong curiosity hook in first 15 seconds.
- Do not invent test results, quotes or statistics.
- Clearly distinguish facts from opinions.
- Provide a unique thesis and practical viewer takeaway.
- Avoid generic "AI news roundup" structure.
- Produce 8 scenes.
- Produce 3 Shorts.
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
"sources": ["..."]
}}
"""
    package = json_response(client, prompt)
    (WORK / "package.json").write_text(json.dumps(package, indent=2), encoding="utf-8")
    return package

def quality_gate(package):
    client = openai_client()
    prompt = f"""
Act as a strict YouTube editorial/YPP quality gate.
Review this package:
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
 "fixes": []
}}

Fail if it is generic filler, fabricated, mainly copied from other creators,
mass-produced/repetitive, or lacks a clear original contribution.
"""
    gate = json_response(client, prompt)
    (WORK / "quality_gate.json").write_text(json.dumps(gate, indent=2), encoding="utf-8")
    return gate

def produce():
    if not APPROVED_TOPIC:
        raise SystemExit("APPROVED_TOPIC is missing.")
    package = build_package(APPROVED_TOPIC)
    gate = quality_gate(package)
    if not gate.get("pass"):
        raise SystemExit("Quality gate failed. See workspace/quality_gate.json.")

    # Production is deliberately separated from publishing.
    # This first cloud version creates the editorial package and leaves
    # rendering/publishing to the next controlled stage.
    body = f"""# uncommonAI — production ready

<!-- uncommonai-production -->

## {package['title']}

Quality gate: **PASS**

Originality: {gate.get('originality')}
Viewer value: {gate.get('viewer_value')}
Evidence quality: {gate.get('evidence_quality')}

The package is stored in the workflow artifact.

### Final approval
Comment **PUBLISH** on this issue only after reviewing the artifact.

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
