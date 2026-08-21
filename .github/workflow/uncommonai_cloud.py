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
practical technology explained clearly without unnecessary hype.

APPROVED TOPIC:
{topic}

CRITICAL TOPIC LOCK:
The approved concept above is the ONLY subject of this video.
Do not replace it with a different topic, trend, list, or angle.

EDITORIAL DIRECTION FOR THIS TOPIC:

If the approved topic is:
"5 AI Tools Actually Changing Productivity in 2026"

frame the video more accurately as:
"5 Tools Actually Changing Productivity in 2026"

Do NOT describe all five products as "AI tools" if some are primarily
developer, research, visual communication, or workflow automation products.
It is acceptable for a productivity tool to use AI without being primarily
an AI product.

For this topic, use exactly these five products:
1. Claude Code
2. Perplexity Pro
3. Cursor
4. Napkin AI
5. Make.com

FACTUAL SAFETY — IMPORTANT:

CURSOR:
Do NOT claim that Cursor uses a "local vector database" unless a specific
authoritative source directly supports that implementation detail.

Prefer:
"Cursor indexes and understands your codebase so its AI features can work
across related files."

PERPLEXITY:
Do NOT claim that Perplexity "aggregates multiple model architectures" or
"enforces citation-backed synthesis."

Prefer:
"Perplexity combines web search with AI-generated answers and citations,
making it useful when users need to trace claims back to sources."

MAKE.COM:
Do NOT call Make.com primarily an AI product.
Describe it as a workflow automation and integration platform that can
incorporate AI into automated workflows.

GENERAL FACTUAL RULES:
- Never invent statistics, benchmarks, customer results, quotes, capabilities,
  internal architecture, or productivity gains.
- If a capability cannot be supported by an authoritative source, omit it or
  clearly label it as interpretation.
- Separate verified product facts from your own analysis.
- Prefer conservative wording over impressive but unsupported claims.

CONTENT REQUIREMENTS:

For every product:
1. State the exact product name.
2. Explain what it actually does.
3. Give one concrete real-world workflow.
4. Give one practical example a viewer could understand.
5. Identify who benefits.
6. Explain at least one meaningful limitation or trade-off.
7. Include a relevant primary source supporting the product claims.

BAD:
"This tool dramatically improves productivity."

GOOD:
"A developer can use Claude Code inside a repository to inspect files,
run tests, investigate an error and review proposed code changes."

Avoid vague marketing phrases such as:
- "changing everything"
- "the future is here"
- "game changer"
- "revolutionizing work"
- "verified productivity gains"
- "cutting through the hype"

The video should feel like an informed practitioner explaining:
"What can I actually do with these tools today, and where should I still
be careful?"

SOURCES:
- Use 5-8 sources.
- Sources must be specific and directly relevant.
- Prefer official product documentation, official product pages, official
  announcements, official help pages, or specific technical papers.
- Do NOT use generic company homepages when a specific source exists.
- The "sources" field must contain plain URL strings, never Markdown links.

SCRIPT:
Create approximately 1200-1500 spoken words for a 7-10 minute video.

The script must:
- have a strong first-15-second hook
- show a concrete productivity problem
- introduce all five named products clearly
- provide concrete workflows and examples
- include limitations and trade-offs
- compare when each type of tool is useful
- contain original explanation and analysis
- end with practical advice

SCENES:
Create exactly 8 scenes.
Every scene must contain:
- narration
- visual_prompt

Each scene must add new information. Do not repeat the same point eight times.

SHORTS:
Create exactly 3 distinct Shorts.
Each Short must:
- have a unique title
- have a self-contained script
- have a distinct takeaway
- have a visual_prompt
- NOT simply copy a paragraph from the main script

YOUTUBE / YPP QUALITY:
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
The "sources" field must contain plain URL strings.

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

FINAL SELF-REVIEW:
Before returning JSON, verify:
- Is the entire package about the approved topic?
- If five tools are requested, are exactly five real products explicitly named?
- Are Claude Code, Perplexity Pro, Cursor, Napkin AI and Make.com clearly named
  for the productivity topic above?
- Is Make.com described as workflow automation rather than an AI product?
- Did you avoid the unsupported Cursor "local vector database" claim?
- Did you avoid the unsupported Perplexity "multiple model architectures" claim?
- Does every product have a concrete use case and limitation?
- Does every important product claim have a supporting source?
- Are sources specific rather than generic homepages?
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

    if len(package.get("sources", [])) < 5:
        raise SystemExit("Production package must contain at least 5 sources.")

    (WORK / "package.json").write_text(
        json.dumps(package, indent=2),
        encoding="utf-8"
    )

    return package


def quality_gate(package):
    prompt = f"""
Act as a strict YouTube editorial, factuality, originality, and YPP-quality
reviewer.

Review this production package:

{json.dumps(package, indent=2)}

The intended topic is:
"5 AI Tools Actually Changing Productivity in 2026"

For editorial accuracy, the preferred framing is:
"5 Tools Actually Changing Productivity in 2026"

The five expected products for this specific topic are:
- Claude Code
- Perplexity Pro
- Cursor
- Napkin AI
- Make.com

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

REVIEW REQUIREMENTS:

1. Do not fail merely because the video discusses AI, AI tools, or AI
   limitations.

2. Reward concrete technical explanations, practical workflows, comparisons,
   limitations, and original analysis.

3. FAIL generic filler, copied/rephrased content, unsupported claims,
   repetitive content, fabricated capabilities, or misleading claims.

4. For this topic, verify that the five products are explicitly named:
   Claude Code, Perplexity Pro, Cursor, Napkin AI and Make.com.

5. Do not accept generic labels such as "Tool number one" instead of product
   names.

6. Each product must have a concrete real-world use case and a meaningful
   limitation or trade-off.

7. At least 3 sources must be specific primary/technical URLs. Preferably
   there should be a specific source for each product.

8. Generic root domains such as openai.com, google.com, or anthropic.com do
   not count as strong evidence when a specific product/documentation URL
   should have been supplied.

9. Check whether important product capabilities are actually supported by
   the provided sources.

10. Penalize vague marketing claims such as "verified productivity gains",
    "revolutionizing work", or "game changer" when no evidence is provided.

11. Do NOT require unsupported internal implementation details.

12. Specifically flag these claims if they appear without authoritative
    support:
    - Cursor uses a "local vector database"
    - Perplexity "aggregates multiple model architectures"
    - Perplexity "enforces citation-backed synthesis"

13. Make.com is primarily a workflow automation/integration platform.
    Do NOT fail the package because it is not primarily an AI product.
    The topic is about productivity tools, and a tool can incorporate AI
    without being an AI product.

14. The title must accurately represent what the video actually contains.
    A title such as "5 Tools Actually Changing Productivity in 2026" is
    acceptable and may be preferable to misleadingly calling every product
    an AI product.

15. The hook should provide a concrete productivity problem or before/after
    contrast rather than generic AI hype.

16. The main script should contain enough substantive material for a
    7-10 minute video and approximately 1200-1500 spoken words.

17. The eight scenes should add new information rather than repeat the same
    point.

18. The three Shorts should have genuinely different takeaways.

19. The package should feel like an informed technical creator explaining
    useful workflows, not mass-produced AI content.

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
