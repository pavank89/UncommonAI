import os, json, re, urllib.request
from pathlib import Path
import feedparser

# GitHub Actions runs this script from the repository root.
# Keep generated artifacts in <repo>/workspace/.
ROOT = Path.cwd()
WORK = ROOT / "workspace"
WORK.mkdir(parents=True, exist_ok=True)

MODE = os.getenv("UNCOMMONAI_MODE", "research").lower()
APPROVED_TOPIC = os.getenv("APPROVED_TOPIC", "").strip()

def safe_text(value):
    """Normalize a value for validation and on-screen use."""
    return re.sub(r"\s+", " ", str(value or "")).strip()

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
You are the senior editorial producer for the faceless YouTube channel uncommonAI.

Your job is NOT to make a generic AI-news slideshow. Create one distinctive,
viewer-first story that could compete with a strong technology creator.

APPROVED TOPIC:
{topic}

Create exactly ONE original 7-10 minute YouTube video package.

==================== ORIGINALITY ====================
Build a clear original thesis around the approved topic.

Do NOT:
- rewrite a source article;
- paraphrase another creator's framing;
- produce a generic "AI is changing everything" story;
- use filler transitions;
- invent statistics, quotes, benchmarks, tests, demos or capabilities.

DO:
- explain WHY the topic matters;
- add interpretation and practical implications;
- distinguish verified facts from analysis;
- identify a limitation, trade-off, failure mode or surprising consequence;
- use concrete technologies, workflows, users, businesses or mechanisms where supported;
- make the conclusion specific and useful.

The viewer should finish with at least one insight they would not get
from simply reading the source headline.

==================== STORY ====================
Use this 8-scene editorial arc:

1. Hook — surprising question, tension, failure, result or implication.
2. Context — why the viewer should care now.
3. Evidence — what is actually known or demonstrated.
4. Mechanism — explain how/why it works.
5. Real-world implication — what changes for users/businesses/developers.
6. Limitation or failure mode — what the hype gets wrong.
7. Practical takeaway — what the viewer should do or watch next.
8. Memorable conclusion — one strong final idea.

Avoid:
- "In today's video"
- "Let's dive in"
- generic AI hype
- repetitive scene introductions
- unsupported claims
- copied source headlines

==================== VISUAL STORYTELLING ====================
Create EXACTLY 8 scenes.

Every scene MUST contain:
- narration
- visual_prompt
- key_phrase: 3-8 words
- visual_type

Allowed visual_type values:
- hook
- comparison
- process
- timeline
- evidence
- warning
- takeaway

The visual_type must describe the INFORMATION RELATIONSHIP, not merely a
color, style or background.

Examples:
- comparison = A vs B, old vs new, human vs AI, before vs after
- process = sequential workflow or mechanism
- timeline = progression across time/stages
- evidence = source/claim/finding relationship
- warning = failure, risk, limitation or breakdown
- takeaway = final decision, recommendation or conclusion
- hook = visually striking opening concept

CRITICAL VISUAL DIVERSITY RULES:
- Use at least 5 DIFFERENT visual_type values across the 8 scenes.
- Never use the same visual_type in adjacent scenes.
- Do not make eight versions of a dark text card.
- Do not repeat the same diagram composition.
- Do not use generic INPUT -> PROCESS -> OUTPUT unless that relationship
  is genuinely the point of the scene.
- Prefer diagrams, comparisons, timelines, evidence chains, failure paths,
  decision structures and concrete workflows.
- Each visual_prompt must describe meaningful labels/elements from THAT scene.
- Never invent numerical chart values. If there is no real data, use a
  conceptual visualization instead of a fake graph.

The visuals must help explain the narration, not merely decorate it.

==================== TITLE ====================
Create 3 possible titles internally and return the strongest one.

The chosen title MUST:
- clearly describe the actual story;
- contain the important topic/entity;
- create curiosity without clickbait;
- normally be 45-75 characters;
- never be "uncommonAI" or a generic AI title.

Also create:
- thumbnail_text: 2-6 words;
- thumbnail_prompt: one strong visual concept, not a text-heavy slide.

==================== SHORTS ====================
Create exactly 3 genuinely different Shorts.

Each Short MUST:
- be 25-55 seconds;
- have a different hook;
- focus on a different insight;
- be self-contained;
- end with a useful takeaway;
- NOT simply cut down scenes 1/2/3;
- contain no unsupported claims.

Each Short needs:
- title
- hook
- script
- visual_prompt

==================== SOURCES ====================
Include original source URLs in "sources".
Never invent URLs. If a source URL is unavailable, do not fabricate one.

==================== JSON ====================
Return VALID JSON ONLY. No markdown fences. No comments.
Every object key MUST use double quotes.

Schema:
{{
  "title_options": ["...", "...", "..."],
  "chosen_title": "...",
  "title": "...",
  "thumbnail_text": "...",
  "description": "...",
  "tags": ["..."],
  "thumbnail_prompt": "...",
  "script": "complete long-form narration",
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

    package = parse_json(gemini_generate(prompt))

    if not isinstance(package, dict):
        raise SystemExit("Gemini production response is not a JSON object.")

    # Normalize title fields for compatibility with the existing renderers.
    title = safe_text(package.get("chosen_title") or package.get("title"))
    if not title:
        raise SystemExit("Gemini did not generate a specific video title.")

    package["title"] = title
    package["chosen_title"] = title

    scenes = package.get("scenes") or []
    shorts = package.get("shorts") or []

    if len(scenes) != 8:
        raise SystemExit(f"Expected 8 scenes, found {len(scenes)}")
    if len(shorts) != 3:
        raise SystemExit(f"Expected 3 Shorts, found {len(shorts)}")

    allowed_visual_types = {
        "hook",
        "comparison",
        "process",
        "timeline",
        "evidence",
        "warning",
        "takeaway",
    }

    # Normalize missing key phrases instead of failing an otherwise valid
    # Gemini response.
    for i, scene in enumerate(scenes, 1):
        if not safe_text(scene.get("narration")):
            raise SystemExit(f"Scene {i} has no narration.")

        key_phrase = safe_text(scene.get("key_phrase"))
        if not key_phrase:
            source = (
                scene.get("visual_prompt")
                or scene.get("narration")
                or ""
            )
            words = safe_text(source).split()
            key_phrase = " ".join(words[:6]).strip(" ,.;:!?")
            if not key_phrase:
                key_phrase = f"Key insight {i}"
            scene["key_phrase"] = key_phrase
            print(
                f"Scene {i}: missing key_phrase; generated fallback: "
                f"{key_phrase}"
            )

        visual_type = safe_text(scene.get("visual_type")).lower()
        if visual_type not in allowed_visual_types:
            raise SystemExit(
                f"Scene {i} has invalid visual_type: {visual_type!r}. "
                f"Allowed: {sorted(allowed_visual_types)}"
            )

        if not safe_text(scene.get("visual_prompt")):
            raise SystemExit(f"Scene {i} has no visual_prompt.")

        scene["visual_type"] = visual_type

    visual_types = [scene["visual_type"] for scene in scenes]
    unique_visual_types = len(set(visual_types))

    if unique_visual_types < 5:
        raise SystemExit(
            "Insufficient visual diversity: "
            f"{unique_visual_types} unique visual types across 8 scenes. "
            "Gemini must use at least 5 different visual types."
        )

    # Gemini can occasionally repeat a visual type even when instructed not to.
    # Repair adjacent duplicates deterministically instead of failing production.
    preferred_by_scene = [
        "hook",
        "comparison",
        "process",
        "evidence",
        "warning",
        "timeline",
        "process",
        "takeaway",
    ]

    for i in range(1, len(scenes)):
        if scenes[i]["visual_type"] == scenes[i - 1]["visual_type"]:
            current = scenes[i]["visual_type"]
            candidates = [
                preferred_by_scene[i],
                "comparison",
                "process",
                "timeline",
                "evidence",
                "warning",
                "takeaway",
                "hook",
            ]

            replacement = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate != current
                    and candidate != scenes[i - 1]["visual_type"]
                ),
                None,
            )

            if replacement:
                print(
                    f"Scene {i + 1}: repaired adjacent visual_type "
                    f"{current!r} -> {replacement!r}"
                )
                scenes[i]["visual_type"] = replacement

    visual_types = [scene["visual_type"] for scene in scenes]

    # Require meaningful diversity, but allow the repair logic above to
    # produce a valid package instead of making Gemini's occasional
    # formatting mistake fatal.
    unique_visual_types = len(set(visual_types))
    if unique_visual_types < 5:
        raise SystemExit(
            "Insufficient visual diversity after repair: "
            f"{unique_visual_types} unique visual types across 8 scenes. "
            "At least 5 are required."
        )

    phrases = [safe_text(s.get("key_phrase")).lower() for s in scenes]
    if len(set(phrases)) < 6:
        raise SystemExit(
            "Scene key phrases are too repetitive; at least 6 unique "
            "key phrases are required."
        )

    package["scenes"] = scenes
    package["shorts"] = shorts

    (WORK / "package.json").write_text(
        json.dumps(package, indent=2),
        encoding="utf-8",
    )

    print(
        "Production package generated: "
        f"{len(scenes)} scenes, {unique_visual_types} visual types."
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
