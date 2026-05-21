"""Vertex RAG tool for the Events agent — retrieve context from the Managed RAG Corpus."""

import logging
import os
import re
import sys

_events_agent_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _events_agent_root not in sys.path:
    sys.path.insert(0, _events_agent_root)

_logger = logging.getLogger(__name__)

# Lines/substrings typical of scraped marketing pages — drop so the model sees facts, not chrome.
_UI_LINE_SUBSTRINGS = (
    "visit event website",
    "register now",
    "view pricing",
    "your browser does not support",
    "html5 video",
    "share this session",
    "gtm tracking",
    "modal open",
    "modal for",
    "don't delete!!",
    "arrow_back",
    "loading...",
    "phase 4 prod",
    "keyboard_arrow",
    "info_outline",
    "star_border",
    "clear filters",
    "sign in to discover",
    "save your favorites",
    "session and activity library",
    "agenda builder",
    "limited-capacity sessions",
    "registrant",
    "*/registrant",
    "session library:",
    "small capacity",
    "book in advance",
    "q&a included",
)
_UI_EXACT_LINES = frozenset(
    {
        "share",
        "close",
        "back",
        "read more",
        "read more.",
        "star",
        "keynotes",
    }
)

# Removed anywhere in the blob (marketing / hero copy often glued to dates on one line).
_MARKETING_PHRASES = (
    "where big ideas become a reality",
    "next has something for everyone",
    "stay ahead of the curve",
    "get a sneak peek into some of the latest advancements in ai and cloud tech",
    "reconnect with innovators",
    "connect with innovators",
    "join a global community of leaders, thinkers, and doers to share ideas",
    "dive into your favorite topics",
    "dive into yourfavorite topics",
    "immerse yourself in three full days of back-to-back lightning talks, interactive demos, guided workshops, and more",
    "relive some of the highlights from next 25",
    "relive some of the highlights from next 2025",
    "arrow_forward_ios",
    "agenda find the times for badge pickup, keynotes, sessions, expo experiences, and more",
    "google cloud next 2026 – las vegas conference",
    "google cloud next 2026 - las vegas conference",
    "think of them as lively conversations, not formal presentations",
    "connect with fellow platform builders for peer-to-peer discussions",
    "learn from others in the trenches",
    "from inspiring keynotes to interactive demos to exclusive networking mixers",
    "dive into the full list of sessions and activities",
    "read more gtm tracking header name present",
    "session contains logic for gtm tracking when modal open",
    "get your ticket",
    "lock in the best price",
    "go to pricing",
    "thank you to our luminary sponsors",
    "thank you to our sponsors",
    "join us to explore the ai and cloud technology",
    "join us to explore",
)


def _strip_session_catalog_ui(text: str) -> str:
    """Strip Next 'Session Library' / agenda filter UI that often dominates RAG chunks."""
    if not text:
        return text
    t = text
    # Header + registrant path noise up to the filter strip
    t = re.sub(
        r"Session Library:\s*Google Cloud Next\s+2026.*?"
        r"(?=Sessions Activities New\s+\d+\s+Results|Session Details:)",
        " ",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    t = re.sub(
        r"Sessions Activities New\s+\d+\s+Results.*?Session Details:",
        "Session Details:",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    t = re.sub(
        r"Session Library:.*?Session Details:",
        "Session Details:",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    t = re.sub(r"phase 4 prod session info\s*\d*\s*", " ", t, flags=re.IGNORECASE)
    t = re.sub(
        r"(Session Details:\s*Google Cloud Next\s+2026\s*)+",
        "Session Details: ",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"(Session Details:\s*)+", "Session Details: ", t, flags=re.IGNORECASE)
    # Some exports omit the second colon: "Session Details: ... Session Details BRK..."
    t = re.sub(r"(?:Session Details:?\s*){2,}", "Session Details: ", t, flags=re.IGNORECASE)
    # Collapse duplicate chrome between session cards
    t = re.sub(r"\bstar\s+star\s+Loading\.\.\.\s*", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bshare\s+Share(\s+Share this session)?\s*", " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def _strip_gde_roster_and_builder_fluff(text: str) -> str:
    """Remove GDE name dumps and 'Google for builders' intro glued into session marketing pages."""
    if not text:
        return text
    t = text
    # Peer roundtable blurb before expert roster
    t = re.sub(
        r"think of them as lively conversations.*?"
        r"(?=the google developer experts speaker lineup|google developer experts speaker lineup)",
        " ",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Long roster: "The Google Developer Experts speaker lineup ... Google for builders"
    t = re.sub(
        r"the google developer experts speaker lineup.*?google for builders",
        " ",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Fallback if anchor wording differs
    t = re.sub(
        r"google developer experts speaker lineup.*?google for builders",
        " ",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # "Whether you're the mastermind ... Next is for you." (often between roster and good session blurbs)
    t = re.sub(
        r"whether you'?re the mastermind behind.*?next is for you\.?",
        " ",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"\s+", " ", t).strip()


_STOPWORDS = frozenset(
    "the a an for to and or is are me my i we you it at be as by on in of if so do "
    "find show give list some any about into from with".split()
)


def _query_keywords(query: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]*", query.lower())
    keys = {w for w in words if len(w) > 2 and w not in _STOPWORDS}
    # Normalize common variants
    if "gen" in keys and "ai" in keys:
        keys.add("generative")
    return keys


def _keyword_score(sentence_lower: str, key: str) -> int:
    """Avoid substring false positives (e.g. 'ai' in 'fair') for short keys."""
    if len(key) <= 3:
        return len(re.findall(rf"(?<!\w){re.escape(key)}(?!\w)", sentence_lower))
    return 1 if key in sentence_lower else 0


def _is_session_discovery_query(query: str) -> bool:
    q = query.lower()
    has_activity = any(
        m in q
        for m in (
            "session",
            "sessions",
            "workshop",
            "workshops",
            "lab",
            "labs",
            "hands-on",
            "hands on",
            "breakout",
            "training",
            "codelab",
        )
    )
    if not has_activity:
        return False
    securityish = bool(
        re.search(
            r"\b(iam|zero\s*trust|identity|security|ciso|threat|soc|compliance|breach|governance)\b",
            q,
        )
    )
    discoveryish = any(
        k in q
        for k in (
            "generative",
            "gen ai",
            "developer",
            "developers",
            "recommend",
            "find ",
            "show me",
            "suggest",
            "topics",
            "track",
            "agenda",
            "list",
            "related",
            "interested",
            "tell me",
            "what are",
            "which sessions",
            "sessions about",
        )
    )
    builder = bool(re.search(r"\b(developer|developers|available)\b", q)) or bool(
        re.search(r"\b(are there|is there|do you have)\b", q)
    )
    labs_or_workshops = bool(re.search(r"\b(workshop|workshops|lab|labs|hands-on|hands on|codelab)\b", q))
    return discoveryish or securityish or builder or labs_or_workshops


def _prioritize_sentences_for_session_query(text: str, query: str, max_chars: int) -> str:
    """Keep sentences most relevant to the user's topic; drop low-scoring marketing filler."""
    keys = _query_keywords(query)
    qlow = query.lower()
    if re.search(r"\bgenerative\b|\bgen\s*ai\b", qlow):
        keys.update({"generative", "gemini", "vertex", "model", "ai"})
    if re.search(
        r"\b(iam|zero\s*trust|identity|security|ciso|threat|soc|compliance|breach|governance)\b",
        qlow,
    ):
        keys.update(
            {
                "security",
                "iam",
                "identity",
                "zero",
                "trust",
                "access",
                "threat",
                "defense",
                "ciso",
                "brk",
                "breakout",
                "proactive",
                "posture",
            }
        )
    for extra in (
        "generative",
        "gemini",
        "vertex",
        "developer",
        "developers",
        "session",
        "sessions",
        "lab",
        "workshop",
        "firebase",
        "flutter",
        "android",
        "kaggle",
    ):
        if _keyword_score(qlow, extra):
            keys.add(extra)
    if re.search(r"\bgo\b", qlow) and (" golang " in f" {qlow} " or " go apps" in qlow or "with go" in qlow):
        keys.add("go")
    if re.search(r"\b(workshop|workshops|lab|labs|hands-on|hands on|codelab)\b", qlow):
        keys.update(
            {
                "workshop",
                "workshops",
                "lab",
                "labs",
                "hands-on",
                "hands",
                "immersive",
                "tutorial",
                "codelab",
            }
        )

    parts = re.split(r"(?<=[.!?])\s+", text)
    scored: list[tuple[int, str]] = []
    for p in parts:
        s = p.strip()
        min_len = 22 if re.search(r"\b[A-Z]{2,}\d*-\d+\b", s) else 35
        if len(s) < min_len:
            continue
        low = s.lower()
        if low.count("google developer expert") >= 2:
            continue
        if "ceo" in low and "google developer expert" in low and "session" not in low:
            continue
        score = sum(_keyword_score(low, k) for k in keys if k)
        # Boost technical session blurbs
        for hint in (
            "gemini",
            "generative",
            "ai-powered",
            "vertex",
            "model",
            "firebase",
            "flutter",
            "android",
            "kaggle",
            "workshop",
            "lab",
            "hands-on",
            "hands on",
            "immersive",
            "tutorial",
            "codelab",
            "zero trust",
            "posture",
            "iam",
            "identity",
            "threat",
            "defense",
            "security",
            "ciso",
        ):
            if hint in low:
                score += 1
        # Breakout / session code lines (often lack IAM in title but are security track)
        if re.search(r"\bbrk\d*-\d+\b.*\bsecurity\b", low):
            score += 4
        elif re.search(r"\bbrk\d*-\d+\b", low) and re.search(
            r"\b(iam|zero|trust|identity|security|ciso|threat|defense|access)\b", qlow
        ):
            score += 3
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    out: list[str] = []
    n = 0
    for _, s in scored:
        if n + len(s) + 1 > max_chars:
            break
        out.append(s)
        n += len(s) + 1
    if not out:
        return text[:max_chars]
    return " ".join(out)


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def _strip_global_noise(text: str) -> str:
    """Strip URLs, capture timestamps, slide markers, known marketing phrases; fix common date OCR glitch."""
    if not text:
        return text
    t = text
    # Material / icon font tokens often appear verbatim in scraped event pages.
    t = re.sub(
        r"\b(?:live_help|av_timer|calendar_clock|data_object|location_on|person|raven|chair|event_seat)\b",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    # "code" icon before labels like "Best for developers" — narrow pattern.
    t = re.sub(r"\bcode\s+Best for developers\b", "Best for developers", t, flags=re.IGNORECASE)
    t = re.sub(r"\bNew\s+data_object\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(
        r"Get your ticket\b.*?\bGo to pricing\b",
        " ",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    t = re.sub(r"\b(?:now|february|march|april)[^.]*?\$[\d,]+\s*USD\b", " ", t, flags=re.IGNORECASE)
    for meta in (
        "q&a included",
        "30 min",
        "small capacity",
        "book in advance",
    ):
        t = re.sub(re.escape(meta), " ", t, flags=re.IGNORECASE)
    t = re.sub(r"https?://[^\s]+", " ", t, flags=re.IGNORECASE)
    # Capture/export timestamps like 1/30/26, 2:22 AM
    t = re.sub(
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\s*,\s*\d{1,2}:\d{2}\s*[AP]M\b",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    # "1/14Next" style slide indices glued to words
    t = re.sub(r"\b\d/\d+(?=[A-Za-z])", " ", t)
    # Typo in scraped Next site: April 2224 -> April 22–24
    t = re.sub(r"\bApril\s+2224\b", "April 22–24", t, flags=re.IGNORECASE)
    # Modal/UI trace artifacts seen inline with session descriptions.
    t = re.sub(r"\bRead more\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bClose\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bGTM Tracking Header name present\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bSession contains logic for gtm tracking when modal open\b", " ", t, flags=re.IGNORECASE)
    for phrase in _MARKETING_PHRASES:
        t = re.sub(re.escape(phrase), " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _dedupe_sentences(text: str, min_len: int = 25) -> str:
    """Drop repeated sentences (common when multiple RAG chunks repeat the same marketing block)."""
    # Split on period followed by space or end; keep it simple for English snippets
    raw_parts = re.split(r"(?<=[.!?])\s+", text)
    seen: set[str] = set()
    out: list[str] = []
    for p in raw_parts:
        s = p.strip()
        if len(s) < min_len:
            continue
        key = re.sub(r"\s+", " ", s).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return " ".join(out).strip()


def _is_logistics_when_where_query(query: str) -> bool:
    q = query.lower()
    needles = (
        "when and where",
        "when is",
        "where is",
        "where does",
        "taking place",
        "what date",
        "what dates",
        "which date",
        "venue",
        "location",
        "held ",
        "when's ",
        "whens ",
    )
    return any(n in q for n in needles)


def _logistics_facts_only(cleaned_blob: str) -> str | None:
    """
    If we can infer dates + place from corpus text, return a short tool payload so the model
    cannot paste speaker rosters or marketing (when/where style questions).
    """
    if not cleaned_blob or len(cleaned_blob) < 12:
        return None
    text = cleaned_blob
    event = None
    if re.search(r"Google\s+Cloud\s+Next\s+2026", text, re.IGNORECASE):
        event = "Google Cloud Next 2026"
    elif re.search(r"Google\s+Cloud\s+Next", text, re.IGNORECASE):
        event = "Google Cloud Next"

    date_s = None
    m = re.search(
        r"April\s+22\s*[–\-]\s*24\s*,?\s*2026|April\s+22–24\s*,?\s*2026",
        text,
        re.IGNORECASE,
    )
    if m:
        date_s = "April 22–24, 2026"
    elif re.search(r"April\s+2224", text, re.IGNORECASE):
        date_s = "April 22–24, 2026"

    venue = None
    if re.search(r"Mandalay\s+Bay\s+Convention\s+Center", text, re.IGNORECASE):
        venue = "Mandalay Bay Convention Center"
    elif re.search(r"Mandalay\s+Bay", text, re.IGNORECASE):
        venue = "Mandalay Bay Convention Center"

    city = "Las Vegas" if re.search(r"Las\s+Vegas", text, re.IGNORECASE) else None

    if not (date_s or venue or city):
        return None

    # Single fluent sentence so UIs that surface raw tool output still look acceptable.
    ev = event or "Google Cloud Next"
    when = date_s or "dates to be confirmed in the event materials"
    where_bits: list[str] = []
    if venue:
        where_bits.append(venue)
    if city:
        where_bits.append(city)
    if city == "Las Vegas":
        where_bits.append("Nevada, USA")
    where = ", ".join(where_bits) if where_bits else "location per event materials"

    # One clean sentence only (many UIs echo tool output verbatim).
    return f"{ev} is scheduled for {when} at {where}."


def _sanitize_rag_text(text: str) -> str:
    """Remove HTML, obvious UI/marketing lines, and duplicate paragraphs from retrieved chunks."""
    if not text or not text.strip():
        return text
    text = _strip_html_tags(text)
    lines_out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(s in low for s in _UI_LINE_SUBSTRINGS):
            continue
        if low in _UI_EXACT_LINES or len(stripped) <= 2:
            continue
        # Drop standalone marketing section headers with no detail on same line
        if low in ("featured speakers", "subject to change.", "(subject to change.)"):
            continue
        lines_out.append(stripped)
    merged = "\n".join(lines_out)
    return _dedupe_paragraphs(merged)


def _dedupe_paragraphs(text: str) -> str:
    blocks = re.split(r"\n\s*\n+", text)
    seen: set[str] = set()
    out: list[str] = []
    for b in blocks:
        chunk = " ".join(b.split()).strip()
        if len(chunk) < 4:
            continue
        key = chunk.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    # Also drop consecutive duplicate lines inside a block (single newlines)
    result_lines: list[str] = []
    prev_low: str | None = None
    for line in "\n".join(out).splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if low == prev_low:
            continue
        prev_low = low
        result_lines.append(line)
    return "\n".join(result_lines)


def _light_clean_chunk(text: str) -> str:
    """Less aggressive than full sanitize — use when line-based filtering empties all chunks."""
    x = _strip_html_tags(text)
    x = _strip_session_catalog_ui(x)
    x = _strip_gde_roster_and_builder_fluff(x)
    x = _strip_global_noise(x)
    return " ".join(x.split()).strip()


def _extract_session_entries(text: str, query: str, limit: int = 12) -> list[str]:
    """Extract concise session entries from noisy corpus text."""
    if not text:
        return []
    # Match common breakout/session shape: "BRK2-139 Security Title ...".
    pattern = re.compile(
        r"\b([A-Z]{2,}\d*-\d+)\s+([A-Za-z][^.!?]{8,180})",
        flags=re.IGNORECASE,
    )
    qlow = query.lower()
    wants_security = bool(re.search(r"\b(iam|zero\s*trust|identity|security)\b", qlow))
    out: list[str] = []
    seen_codes: set[str] = set()
    for m in pattern.finditer(text):
        code = m.group(1).upper()
        title = " ".join(m.group(2).split()).strip(" -:;,.")
        low = title.lower()
        if len(title) < 8:
            continue
        if any(k in low for k in ("keyboard_arrow", "info_outline", "star_border", "results clear filters")):
            continue
        if wants_security and not re.search(r"\b(security|iam|identity|zero trust|trust|access|ciso|threat)\b", low):
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)
        out.append(f"{code}: {title}")
        if len(out) >= limit:
            break
    return out


def _retrieval_plan(user_query: str, top_k: int, threshold: float) -> list[tuple[str, int, float]]:
    """
    Primary query first; then broader / looser attempts if the corpus uses different wording
    than the user's phrasing (common for session-discovery vs marketing-page chunks).
    Higher vector_distance_threshold = allow less-similar chunks (Vertex RAG API semantics).
    """
    q = user_query.strip()
    plans: list[tuple[str, int, float]] = [(q, top_k, threshold)]

    if _is_session_discovery_query(user_query):
        if re.search(
            r"\b(iam|zero\s*trust|identity|security|ciso|threat|soc|compliance|breach|governance)\b",
            user_query,
            re.IGNORECASE,
        ):
            sec_broad = (
                "Google Cloud Next security IAM identity zero trust access management CISO "
                "breakout BRK session threat defense governance compliance workshop"
            )
            plans.append((sec_broad, max(top_k, 10), min(0.94, threshold + 0.38)))
        if re.search(
            r"\b(workshop|workshops|lab|labs|hands-on|hands on|codelab)\b",
            user_query,
            re.IGNORECASE,
        ):
            lab_broad = (
                "Google Cloud Next workshops labs hands-on immersive learning center skills zone "
                "developer training codelab technical classroom sandbox"
            )
            plans.append((lab_broad, max(top_k, 10), min(0.94, threshold + 0.36)))
        broad = (
            "Google Cloud Next developer sessions workshops labs AI Gemini artificial intelligence "
            "generative Android Firebase Flutter Kaggle machine learning technical builders"
        )
        plans.append((broad, max(top_k, 8), min(0.92, threshold + 0.35)))
        plans.append((broad, max(top_k, 12), min(0.98, float(os.getenv("VERTEX_RAG_VECTOR_DISTANCE_THRESHOLD_MAX", "0.98")))))
    else:
        # Same query, looser threshold + more chunks (handles slightly off embeddings)
        plans.append(
            (
                q,
                max(top_k, 8),
                min(
                    float(os.getenv("VERTEX_RAG_VECTOR_DISTANCE_THRESHOLD_MAX", "0.98")),
                    threshold + 0.35,
                ),
            )
        )

    return plans


def _build_corpus_name() -> str:
    """
    Resolve RagCorpus resource name from environment.

    Supported envs:
    - `VERTEX_RAG_CORPUS_NAME`: full resource name, e.g.
      `projects/<project>/locations/<location>/ragCorpora/<corpus_id>`
    - `VERTEX_RAG_CORPUS_ID` + `VERTEX_RAG_PROJECT_ID` + `VERTEX_RAG_LOCATION`
      (or fallback to `GCP_PROJECT_ID`/`GCP_LOCATION`).
    """

    corpus_name = (os.getenv("VERTEX_RAG_CORPUS_NAME") or "").strip()
    if corpus_name:
        return corpus_name

    corpus_id = (os.getenv("VERTEX_RAG_CORPUS_ID") or "").strip()
    project_id = (os.getenv("VERTEX_RAG_PROJECT_ID") or os.getenv("GCP_PROJECT_ID") or "").strip()
    location = (os.getenv("VERTEX_RAG_LOCATION") or os.getenv("GCP_LOCATION") or "us-west1").strip()

    if project_id and location and corpus_id:
        return f"projects/{project_id}/locations/{location}/ragCorpora/{corpus_id}"

    # Last resort: corpus for primary project agentic-prismv333 (set VERTEX_RAG_CORPUS_NAME for other projects).
    return "projects/agentic-prismv333/locations/us-west1/ragCorpora/6917529027641081856"


def retrieve_event_info(query: str) -> str:
    """Retrieve relevant event information from the Managed RAG Corpus.

    Args:
        query: Natural language question or topic to look up in the corpus.

    Returns:
        Concatenated text from the top retrieved contexts, or a fallback message
        if retrieval fails or returns no contexts.
    """
    # Resolve at call time so Agent Engine env_vars (injected at deploy) apply; avoid stale import-time defaults.
    corpus_name = _build_corpus_name()
    rag_project = (os.getenv("VERTEX_RAG_PROJECT_ID") or os.getenv("GCP_PROJECT_ID") or "agentic-prismv333").strip()
    rag_location = (os.getenv("VERTEX_RAG_LOCATION") or os.getenv("GCP_LOCATION") or "us-west1").strip()
    similarity_top_k = int(os.getenv("VERTEX_RAG_SIMILARITY_TOP_K", "5"))
    vector_distance_threshold = float(os.getenv("VERTEX_RAG_VECTOR_DISTANCE_THRESHOLD", "0.5"))

    try:
        try:
            from vertex_init import init_vertexai

            init_vertexai(rag_project, rag_location)
            import vertexai
            from vertexai.preview import rag
        except Exception as e:
            print(f"ERROR: RAG Init failed: {e}")
            _logger.warning(
                "events_rag_init_failed error=%s corpus=%s",
                type(e).__name__,
                corpus_name.rsplit("/", 1)[-1][:24] if corpus_name else "",
            )
            return f"No relevant information found. (System Error: Init failed: {e})"

        try:
            resource = rag.RagResource(rag_corpus=corpus_name)
            response = None
            for rq, rtop, rthresh in _retrieval_plan(query, similarity_top_k, vector_distance_threshold):
                try:
                    response = rag.retrieval_query(
                        text=rq,
                        rag_resources=[resource],
                        similarity_top_k=rtop,
                        vector_distance_threshold=rthresh,
                    )
                except Exception as e:
                    print(f"ERROR: RAG Retrieval attempt failed ({rq[:80]}...): {e}")
                    response = None
                    continue
                if response and response.contexts and response.contexts.contexts:
                    break
        except Exception as e:
            print(f"ERROR: RAG Retrieval failed: {e}")
            _logger.warning("events_rag_retrieval_failed error=%s", type(e).__name__)
            return f"No relevant information found. (System Error: Retrieval failed: {e})"

        if not response or not response.contexts or not response.contexts.contexts:
            _logger.info("events_rag_miss reason=no_contexts query_len=%s", len((query or "").strip()))
            return "No relevant information found in the corpus."

        raw_chunks = [_strip_html_tags(ctx.text) for ctx in response.contexts.contexts if ctx.text]
        raw_blob = "\n\n".join(c for c in raw_chunks if c.strip())
        raw_blob = _strip_session_catalog_ui(raw_blob)
        raw_blob = _strip_gde_roster_and_builder_fluff(raw_blob)
        raw_blob = _strip_global_noise(raw_blob)

        if _is_logistics_when_where_query(query):
            logistics = _logistics_facts_only(raw_blob)
            if logistics:
                return logistics

        parts: list[str] = []
        for c in raw_chunks:
            x = _strip_session_catalog_ui(c)
            x = _strip_gde_roster_and_builder_fluff(x)
            x = _strip_global_noise(x)
            x = _sanitize_rag_text(x)
            x = _dedupe_sentences(x)
            if x.strip():
                parts.append(x.strip())
        parts = [p for p in parts if p.strip()]
        if not parts:
            # Line-based sanitize can drop entire chunks; keep GDE/marketing stripping only.
            parts = [p for p in (_light_clean_chunk(c) for c in raw_chunks) if p]
        if not parts:
            _logger.info("events_rag_miss reason=sanitize_empty_chunks raw_chunks=%s", len(raw_chunks))
            return "No relevant information found in the corpus."

        merged = "\n\n".join(parts)
        merged = _strip_session_catalog_ui(merged)
        merged = _strip_gde_roster_and_builder_fluff(merged)
        merged = _dedupe_sentences(_strip_global_noise(merged))
        max_chars = int(os.getenv("VERTEX_RAG_TOOL_MAX_CHARS", "4000"))
        session_cap = int(os.getenv("VERTEX_RAG_SESSION_QUERY_MAX_CHARS", "3200"))
        if _is_session_discovery_query(query):
            session_entries = _extract_session_entries(merged, query)
            if session_entries:
                return "Sessions found:\n" + "\n".join(f"- {s}" for s in session_entries)
            merged = _prioritize_sentences_for_session_query(merged, query, min(max_chars, session_cap))
        elif len(merged) > max_chars:
            merged = merged[:max_chars].rsplit(". ", 1)[0] + "."
        _logger.info(
            "events_rag_hit query_len=%s parts=%s merged_len=%s",
            len((query or "").strip()),
            len(parts),
            len(merged),
        )
        return merged
        
    except Exception as e:
        print(f"CRITICAL ERROR in retrieve_event_info: {e}")
        _logger.warning("events_rag_critical_error error=%s", type(e).__name__)
        return f"No relevant information found. (Critical Error: {e})"
