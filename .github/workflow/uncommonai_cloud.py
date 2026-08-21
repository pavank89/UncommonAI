import os, json, re, urllib.request
from pathlib import Path
import feedparser

ROOT = Path.cwd()
WORK = ROOT / "workspace"
WORK.mkdir(parents=True, exist_ok=True)

print(f"ROOT: {ROOT}")
print(f"WORK: {WORK}")

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

    # Remove Markdown code fences if Gemini adds them.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    # First try normal JSON parsing.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to locate the outermost JSON object.
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        print("GEMINI RESPONSE:")
        print(text[:10000])
        raise SystemExit("Gemini did not return a JSON object.")

    candidate = text[start:end + 1]

    # Try the extracted object directly.
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Common Gemini problem: Markdown links inside JSON strings.
    # Convert [text](https://example.com) into https://example.com.
    candidate = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r"\2",
        candidate
    )

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Print the exact response so we can diagnose any remaining problem.
    print("INVALID GEMINI JSON:")
    print(text[:15000])
    print("JSON ERROR:")
    try:
        json.loads(candidate)
    except json.JSONDecodeError as e:
        print(e)

    raise SystemExit("Could not parse Gemini JSON response.")

def build_package(topic):
    prompt = f"""
You are the lead producer for the faceless YouTube channel uncommonAI.

Audience:
Curious professionals, creators, developers and tech enthusiasts who want
important AI developments explained clearly without needing an engineering
background.

APPROVED CONCEPT:
{topic}

CRITICAL TOPIC LOCK:
The approved concept above is the ONLY subject of this video.
Do not replace it with a different topic, trend, list, or angle.
The title, hook, description, script, scenes, Shorts, and sources must all
directly support the approved concept.

Create an ORIGINAL 8-10 minute YouTube package with approximately 1200-1500
spoken words.

RULES:
- Do not rewrite a source article or another creator.
- Give a strong curiosity hook in the first 15 seconds.
- Explain why the development matters to normal people, creators and businesses.
- Simple language first, technical detail second.
- Never invent statistics, quotes, benchmarks, capabilities, experiments,
  customer stories, personal experiences, or productivity gains.
- Separate verified facts from interpretation.
- Use specific real products/tools when the topic is about tools.
- Include specific primary/technical source URLs.
- Avoid generic AI-news roundup structure.
- Avoid vague marketing language such as "changing everything", "cutting through
  the hype", or "verified productivity gains" unless backed by a concrete fact.
- Create exactly 8 scenes and exactly 3 distinct Shorts.
- Return valid JSON only.

TOOL-SPECIFIC REQUIREMENT:
If the approved topic asks for five AI tools, identify EXACTLY FIVE specific,
real AI products/tools.

Do NOT call them "Tool number one", "Tool number two", etc.

For each tool include:
1. Exact product/tool name.
2. What it actually does.
3. One concrete productivity workflow it improves.
4. One concrete example of how a viewer could use it.
5. A specific primary source URL supporting the relevant capability.

The five tools must be meaningfully different.

Do not invent features. If a capability cannot be supported by a source, omit
the claim or clearly label it as interpretation.

SOURCE REQUIREMENT:
Use 4-8 sources.
At least 3 sources must be specific primary/technical URLs such as:
- exact product documentation
- exact GitHub repository
- exact research paper
- official product announcement
Do not use generic company homepages when a specific source exists.

NARRATIVE:
Scene 1 — concrete hook and the problem.
Scene 2 — explain the workflow/problem.
Scene 3 — introduce the first concrete tool or mechanism.
Scene 4 — continue with concrete tools and use cases.
Scene 5 — limitations/trade-offs.
Scene 6 — evidence and technical explanation.
Scene 7 — practical comparison or decision framework.
Scene 8 — conclusion with actionable advice.

Each scene must add new information. Do not repeat the same point eight times.

SHORTS:
Create 3 genuinely different Shorts. Each must have its own takeaway and must
not simply copy a paragraph from the main script.

YOUTUBE/YPP QUALITY:
- No copied scripts.
- No article compilation.
- No repetitive filler.
- No fabricated claims.
- No misleading title or thumbnail.
- Provide meaningful original explanation and analysis.
- The package should feel like an experienced technical creator explaining
  something useful, not mass-produced AI content.

JSON REQUIREMENTS:
Return ONLY one valid JSON object.
Do not use Markdown code fences.
Do not include text before or after the JSON.
Every array and object must be properly closed.
Do not use trailing commas.
The "sources" field must contain plain URL strings, never Markdown links.

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
    {{"narration":"...", "visual_prompt":"..."}}
  ],
  "shorts": [
    {{"title":"...", "script":"...", "visual_prompt":"..."}}
  ],
  "sources": ["https://..."]
}}

FINAL SELF-REVIEW BEFORE RETURNING JSON:
- Is the entire package about the approved concept?
- If five tools are requested, are exactly five real tools explicitly named?
- Does each named tool have a concrete use case?
- Does each named tool have a specific supporting source?
- Did you avoid labels such as "Tool number one"?
- Did you avoid unsupported productivity/performance claims?
- Are at least 3 sources specific primary/technical URLs?
- Are the failure modes/trade-offs concrete?
- Does every scene add something new?
- Are the three Shorts genuinely different?
- Is the main script approximately 1200-1500 spoken words?
"""
    package = parse_json(gemini_generate(prompt))

    if not isinstance(package, dict):
        raise SystemExit("Production package is not a JSON object.")

    required = [
        "title_options",
        "chosen_title",
        "hook",
        "description",
        "tags",
        "thumbnail_prompt",
        "script",
        "scenes",
        "shorts",
        "sources",
    ]

    missing = [key for key in required if not package.get(key)]
    if missing:
        raise SystemExit(
            "Production package missing: " + ", ".join(missing)
        )

    if len(package.get("scenes", [])) != 8:
        raise SystemExit("Production package must contain exactly 8 scenes.")

    if len(package.get("shorts", [])) != 3:
        raise SystemExit("Production package must contain exactly 3 Shorts.")

    if len(package.get("sources", [])) < 4:
        raise SystemExit("Production package must contain at least 4 sources.")

    (WORK / "package.json").write_text(
        json.dumps(package, indent=2),
        encoding="utf-8"
    )

    return package

def quality_gate(package):
    prompt = f"""
Act as a strict YouTube editorial, factuality, originality, and YPP-quality
reviewer.

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

Score every category from 0-10.

PASS RULE:
pass=true only when:
- originality >= 7
- viewer_value >= 7
- evidence_quality >= 7
- repetition_risk <= 4
- copyright_risk <= 3
- ypp_risk <= 4
- title_quality >= 7
- hook_quality >= 7

Review requirements:

1. Do not fail merely because the video discusses AI tools or AI limitations.
2. Reward concrete technical explanations and original analysis.
3. Fail generic filler, copied/rephrased content, unsupported claims,
   repetitive content, or misleading claims.
4. If the topic asks for five tools, FAIL if the package uses generic labels
   such as "Tool number one" instead of naming five real products.
5. If the topic asks for five tools, FAIL if the tools do not have concrete
   use cases.
6. Check that at least 3 sources are specific primary/technical URLs.
7. Generic root domains such as openai.com, google.com, or anthropic.com
   should not count as strong evidence when a specific product/documentation
   URL should have been supplied.
8. Check that important capabilities are supported by the sources.
9. Penalize vague marketing claims such as "verified productivity gains" when
   no evidence is provided.
10. Penalize generic listicle structure if it provides little original analysis.
11. Do not require a personal experiment unless the package explicitly claims
   to be one. A clearly labeled educational/representative workflow is valid.
12. The title must accurately represent what the video actually contains.
13. The hook should provide a concrete problem or before/after contrast.

If the package fails, provide no more than 5 precise fixes.

Return valid JSON only.
"""
    gate = parse_json(gemini_generate(prompt))

    (WORK / "quality_gate.json").write_text(
        json.dumps(gate, indent=2),
        encoding="utf-8"
    )

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
