import os, json, re, urllib.request
from pathlib import Path
import feedparser

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "workspace"
WORK.mkdir(exist_ok=True)

MODE = os.getenv("UNCOMMONAI_MODE", "research").lower()
APPROVED_TOPIC = os.getenv("APPROVED_TOPIC", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

FEEDS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
}

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
    req = urllib.request.Request("https://api.github.com" + path, data=data, method=method)
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
                    "source": source, "title": title, "url": e.get("link", ""),
                    "published": e.get("published", ""), "summary": summary[:900],
                })
        except Exception as exc:
            print("Feed error:", source, exc)
    return rows

def score_item(r):
    text = (r["title"] + " " + r["summary"]).lower()
    keywords = ["agent","ai","model","openai","google","coding","robot","robotics",
                "computer use","reasoning","image","video","developer","automation",
                "chip","gpu","physical ai"]
    score = sum(2 if k in r["title"].lower() else 1 for k in keywords if k in text)
    for k in ["launch","release","new","demo","open source","available","integration","update","announces"]:
        if k in text: score += 2
    return score

def youtube_angle(title, summary):
    text = (title + " " + summary).lower()
    for keys, angle in ANGLE_RULES:
        if any(k in text for k in keys):
            return angle
    return "What This New AI Development Actually Means for You"

def create_issue(title, body, labels=None):
    return gh_api(f"/repos/{repo()}/issues", "POST",
                  {"title": title, "body": body, "labels": labels or []})

def list_open_issues():
    return gh_api(f"/repos/{repo()}/issues?state=open&per_page=30")

def open_issue_with_marker(marker):
    for i in list_open_issues():
        if marker in i.get("body", ""): return i
    return None

def research():
    rows = collect_news()
    if not rows: raise SystemExit("No research signals found.")
    ranked = sorted(rows, key=score_item, reverse=True)[:12]
    lines = ["# uncommonAI Research", "",
             "Original source headlines are separated from viewer-first concepts.", ""]
    for i, r in enumerate(ranked, 1):
        lines += [f"## {i}. {youtube_angle(r['title'], r['summary'])}",
                  f"- Original source headline: {r['title']}",
                  f"- Source: {r['source']}", f"- Published: {r['published']}",
                  f"- URL: {r['url']}", f"- Evidence/context: {r['summary']}",
                  f"- Research score: {score_item(r)}", ""]
    (WORK / "research.md").write_text("\n".join(lines), encoding="utf-8")

    top = ranked[0]
    marker = "<!-- uncommonai-topic-approval -->"
    body = f"""# uncommonAI topic approval

{marker}

## Recommended YouTube concept

**{youtube_angle(top["title"], top["summary"])}**

### Why this is interesting
{top["summary"]}

### Original source
**{top["title"]}**

Source: {top["url"]}

### Approval
Comment **APPROVE** to start production.
Comment **REJECT** to discard this idea.

No publishing occurs from this approval step.
"""
    if not open_issue_with_marker(marker):
        issue = create_issue("🎬 uncommonAI — approve next video topic", body, ["uncommonai:topic"])
        print("Approval issue:", issue["html_url"])

def gemini_generate(prompt):
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY is missing.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print("GEMINI API ERROR:")
        print(error_body)
        raise

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        print("Unexpected Gemini response:")
        print(json.dumps(data, indent=2))
        raise SystemExit(f"Could not parse Gemini response: {e}")

def parse_json(text):
    text = text.strip()

    # Remove Markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    # Normal JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract the first complete JSON object
    start = text.find("{")
    if start == -1:
        print("GEMINI RESPONSE:")
        print(text[:8000])
        raise SystemExit("Gemini did not return a JSON object.")

    try:
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(text[start:])
        return result
    except json.JSONDecodeError as e:
        print("INVALID GEMINI JSON:")
        print(text[:8000])
        print("JSON ERROR:", e)
        raise SystemExit("Could not parse Gemini JSON response.")

def build_package(topic):
    prompt = f"""
You are the lead producer for the faceless YouTube channel uncommonAI.

Audience:
Curious professionals, QA engineers, developers, creators, and tech enthusiasts
who want practical AI explained clearly without needing an advanced engineering
background.

APPROVED VIDEO CONCEPT:
{topic}

Create an ORIGINAL 7-10 minute YouTube package.

IMPORTANT EDITORIAL STANDARD:
This must feel like a real technical experiment/report, NOT a generic AI-news
video.

The central story must be:
1. A realistic QA workflow.
2. What an AI agent was asked to automate.
3. What the agent successfully automated.
4. What the agent got wrong, misunderstood, or broke.
5. What a human QA engineer still had to do.
6. What this tells us about the real limits of AI agents.

Do NOT pretend that an experiment was personally performed unless the supplied
topic or source material explicitly establishes that it was performed.

If the available evidence does not establish a real-world personal experiment,
frame claims carefully as:
- "In a representative QA workflow..."
- "A practical test would..."
- "Existing agent capabilities suggest..."
rather than falsely claiming first-hand results.

EVIDENCE REQUIREMENTS:
- Prefer specific, verifiable technologies, tools, frameworks, APIs, papers,
  documentation, or primary announcements.
- Examples may include real agent frameworks, browser/computer-use agents,
  coding agents, test-generation systems, CI/CD integrations, or QA automation
  approaches ONLY when they are actually relevant and supported by sources.
- Do not invent tool capabilities.
- Do not invent benchmarks, percentages, test results, quotes, customer stories,
  or personal experiences.
- Do not present hypothetical capabilities as current facts.
- Each important factual claim should be traceable to a source.
- Prefer direct documentation, research papers, GitHub repositories, or primary
  company announcements over generic homepages.
- Include source URLs.

ORIGINALITY:
- Do not rewrite or summarize one article.
- Do not produce a generic "Top AI tools" list.
- Do not use recycled AI-news language.
- Build a coherent argument around the QA workflow.
- Include original explanation, comparison, reasoning, and practical implications.
- Distinguish clearly between verified facts and your analysis.

VIDEO STRUCTURE:
Use a strong narrative rather than a news roundup.

Suggested structure:
Scene 1 — Hook: the surprising QA-agent result.
Scene 2 — The QA task and why it is difficult.
Scene 3 — What the agent was asked to automate.
Scene 4 — What the agent can actually accomplish.
Scene 5 — Where the agent fails or makes mistakes.
Scene 6 — Why those failures happen.
Scene 7 — What still requires a human QA engineer.
Scene 8 — Practical conclusion: where agents help today and where they should
not be trusted blindly.

The first 15 seconds must create curiosity without using generic hooks such as
"If you're still using AI just to write emails."

Use concrete situations and consequences.

TECHNICAL QUALITY:
Explain technical concepts in simple language first, then add technical detail.
Where useful, explain concepts such as:
- test planning
- test generation
- browser/API interaction
- assertions
- debugging
- flaky tests
- environment setup
- CI/CD
- regression testing
- agent memory/state
- tool calling
- human verification

Only include concepts relevant to the actual story.

YOUTUBE/YPP SAFETY:
- No copied scripts.
- No article-by-article compilation.
- No repetitive filler.
- No unsupported claims.
- No fake personal experience.
- No fabricated sources.
- No misleading title or thumbnail.
- The final package must provide meaningful original explanation and analysis.

Create:
- 8 scenes.
- 3 genuinely different Shorts.
- Each Short must have a distinct takeaway rather than simply cutting the
  main script into three pieces.

Return JSON ONLY.

Schema:
{{
"title_options": ["...", "...", "..."],
"chosen_title": "...",
"hook": "...",
"description": "...",
"tags": ["..."],
"thumbnail_prompt": "...",
"script": "...",
"scenes": [
  {{
    "narration": "...",
    "visual_prompt": "..."
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

FINAL CHECK BEFORE RETURNING JSON:
- Is the story concrete rather than generic?
- Are the important claims supported?
- Are the tools/frameworks real and relevant?
- Have you avoided invented experiments and benchmarks?
- Does the video explain what agents can and cannot do in QA?
- Does each scene add new information?
- Are the three Shorts genuinely different?
- Would this provide meaningful original commentary rather than a compilation?
"""
    package = parse_json(gemini_generate(prompt))
    (WORK / "package.json").write_text(
        json.dumps(package, indent=2),
        encoding="utf-8"
    )
    return package

def quality_gate(package):
    prompt = f"""
Act as a strict YouTube editorial and YPP-quality reviewer.

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
"title_quality": 0,
"hook_quality": 0,
"fixes": []
}}

Fail if it is generic filler, mainly copied/rephrased, unsupported, repetitive,
or lacks meaningful original explanation/commentary.
"""
    gate = parse_json(gemini_generate(prompt))
    (WORK / "quality_gate.json").write_text(json.dumps(gate, indent=2), encoding="utf-8")
    return gate

def produce():
    if not APPROVED_TOPIC:
        raise SystemExit("APPROVED_TOPIC is missing.")

    package = build_package(APPROVED_TOPIC)

    gate = quality_gate(package)

    if not gate.get("pass"):
        print("QUALITY GATE RESULT:")
        print(json.dumps(gate, indent=2))
        raise SystemExit("Quality gate failed.")

    title = package.get(
        "chosen_title",
        package.get("title_options", ["UncommonAI video"])[0]
    )

    # Save the complete production package
    (WORK / "production_package.json").write_text(
        json.dumps(package, indent=2),
        encoding="utf-8"
    )

    # Create a human-readable production brief
    body = (
        "# uncommonAI — production ready\n\n"
        f"## Topic\n{APPROVED_TOPIC}\n\n"
        f"## Title\n{title}\n\n"
        "## Production package\n\n"
        "The AI-generated production package has passed the "
        "quality gate and is ready for review.\n\n"
        "Review the accompanying production_package.json artifact "
        "before publishing.\n\n"
        "## Quality gate\n\n"
        f"```json\n{json.dumps(gate, indent=2)}\n```\n"
    )

    (WORK / "production.md").write_text(
        body,
        encoding="utf-8"
    )

    print("Production package created successfully.")
    print(f"Title: {title}")
    print(f"Topic: {APPROVED_TOPIC}")

if __name__ == "__main__":
    if MODE == "research": research()
    elif MODE == "produce": produce()
    else: raise SystemExit("UNCOMMONAI_MODE must be research or produce.")
