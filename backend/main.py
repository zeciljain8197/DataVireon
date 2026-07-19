from fastapi import FastAPI, HTTPException, Header, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from skills.prompts import get_skill, SKILLS
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client
import httpx, os, json, logging, ast, builtins as _builtins, re as _re
from collections import Counter as _Counter
import anthropic as _anthropic
from groq import Groq as _Groq

load_dotenv()

logger = logging.getLogger("datavireon")

app = FastAPI(title="DataVireon API")


from fastapi import Request as _Request
from fastapi.responses import Response as _Response
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: _Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)

# Parse allowed origins from env (comma-separated for multiple)
_raw_origins = os.getenv("FRONTEND_URL", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",")]
# Always allow localhost for development
if "http://localhost:3000" not in _allowed_origins:
    _allowed_origins.append("http://localhost:3000")
# Allow all vercel preview deployments
_allow_origin_regex = r"https://.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://172.23.96.1:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY         = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY or SUPABASE_KEY)

_TOP_LEVEL_DEF_RE = _re.compile(r"^(async\s+def\s+\w|def\s+\w|class\s+\w)")


def _split_into_chunks(lines: list) -> tuple:
    """Split source lines into a header (everything before the first
    top-level def/class) and a list of (name, chunk_lines) for each
    top-level function/class. Uses column-0 line scanning rather than a
    full ast.parse — this has to keep working even when the file has a
    syntax error elsewhere, since files that need this tool's help commonly
    do (that's the whole point of the tool)."""
    starts = []
    for i, line in enumerate(lines):
        if line[:1] not in (" ", "\t", "") and _TOP_LEVEL_DEF_RE.match(line):
            start = i
            j = i - 1
            while j >= 0 and lines[j].startswith("@"):
                start = j
                j -= 1
            starts.append(start)
    starts = sorted(set(starts))

    if not starts:
        return lines, []

    header = lines[:starts[0]]
    chunks = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        chunk_lines = lines[start:end]
        name_line = next((l for l in chunk_lines if _TOP_LEVEL_DEF_RE.match(l)), chunk_lines[0])
        chunks.append((name_line.strip(), chunk_lines))
    return header, chunks


def _cut_at_line_boundary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text.rfind("\n", 0, max_chars)
    return text[:cut] if cut != -1 else text[:max_chars]


def _fallback_trim(lines: list, max_chars: int) -> str:
    """Head/tail/sample trim for content with no detected def/class
    structure (non-Python, or a flat script). Unlike the old
    implementation, this never duplicates content when there are too few
    "lines" to sample sensibly (e.g. one enormous minified single-line
    file — head and tail would otherwise both resolve to that same one
    line) and never cuts mid-line."""
    if len(lines) <= 40:
        return _cut_at_line_boundary("\n".join(lines), max_chars)
    head = lines[:20]
    tail = lines[-20:]
    middle = lines[20:-20]
    if middle:
        step = max(1, len(middle) // 20)
        middle = middle[::step][:20]
    trimmed = "\n".join(head + ["# ... (trimmed for context) ..."] + middle + tail)
    return _cut_at_line_boundary(trimmed, max_chars)


_RELEVANCE_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "our", "your", "their", "his", "her",
    "to", "of", "in", "on", "at", "by", "for", "with", "from", "as", "into", "onto",
    "we", "you", "they", "he", "she", "them", "us", "me", "my", "if", "when", "while",
    "not", "no", "do", "does", "did", "done", "has", "have", "had", "will", "would", "can",
    "could", "should", "may", "might", "must", "also", "then", "than", "some", "any", "all",
    "def", "self", "return", "none", "true", "false",
}
_WORD_RE = _re.compile(r"[a-zA-Z]+")


def _meaningful_words(text: str) -> set:
    """Split on any non-letter (including underscores) so snake_case
    identifiers decompose into their constituent words — train_test_split
    needs to match "splitting" in a natural-language problem statement, and
    a whole-identifier token match never would. Drops stop words and very
    short words so common filler ("the", "an", "if") can't dominate the
    signal over domain-relevant terms (leakage, split, precision)."""
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) > 2 and w not in _RELEVANCE_STOP_WORDS}


def smart_trim_codebase(code: str, max_chars: int = 4000, problem: str = "") -> tuple:
    """Trim an oversized codebase down to max_chars while keeping whatever's
    included STRUCTURALLY COMPLETE (whole functions/classes, never
    fragments) and prioritized by RELEVANCE to the reported problem —
    replaces a fixed head/tail plus an evenly-sampled, frequently
    incoherent slice of the middle that could (and, on any realistically-
    sized file, would) skip the actual buggy function entirely while
    stitching together orphaned fragments elsewhere.

    Returns (trimmed_code, was_trimmed) so callers can warn when the model
    didn't see the whole file."""
    if len(code) <= max_chars:
        return code, False

    lines = code.split("\n")
    header, chunks = _split_into_chunks(lines)
    header_text = "\n".join(header)

    if not chunks:
        return _fallback_trim(lines, max_chars), True

    problem_words = _meaningful_words(problem) if problem else set()
    chunk_word_sets = [_meaningful_words(name + " " + " ".join(chunk_lines)) for name, chunk_lines in chunks]
    # IDF-style weighting: a problem word shared by many chunks (e.g. a
    # phrase repeated across a batch of near-identical helper functions) is
    # weak, easily-coincidental evidence — with enough such chunks, that
    # alone can outvote a genuinely relevant function that just doesn't
    # happen to share any words with the problem statement. A word that
    # appears in only one or two chunks is a much stronger, more
    # distinctive signal, so it's weighted far higher.
    doc_freq = {w: sum(1 for ws in chunk_word_sets if w in ws) for w in problem_words}

    def _weighted_score(chunk_words: set) -> float:
        matches = chunk_words & problem_words
        return sum(1.0 / doc_freq[w] for w in matches if doc_freq.get(w, 0) > 0)

    base_scores = [_weighted_score(ws) for ws in chunk_word_sets]

    # Propagate relevance across simple call relationships: a low-level
    # helper with the actual bug commonly shares no vocabulary at all with a
    # symptom-level problem statement, but if a highly-relevant function
    # calls it (or is called by it), that call relationship is itself real
    # evidence — in both directions, since the caller is the context needed
    # to understand why the callee matters, and vice versa.
    chunk_names_only = [
        name.split("(")[0].replace("async ", "").replace("def ", "").replace("class ", "").strip()
        for name, _ in chunks
    ]
    call_pairs = [
        (i, j)
        for i, (_, lines_i) in enumerate(chunks)
        for j, callee_name in enumerate(chunk_names_only)
        if i != j and callee_name and f"{callee_name}(" in " ".join(lines_i)
    ]
    # Multiple hops so relevance flows transitively through a call chain
    # (main -> train_model -> preprocess), each pass building on the
    # previous one's updated scores rather than only the original ones.
    propagated = list(base_scores)
    for _hop in range(3):
        next_scores = list(propagated)
        for i, j in call_pairs:
            next_scores[j] = max(next_scores[j], propagated[i] * 0.5)
            next_scores[i] = max(next_scores[i], propagated[j] * 0.5)
        propagated = next_scores

    scored = [
        (name, chunk_lines, propagated[idx], len("\n".join(chunk_lines)))
        for idx, (name, chunk_lines) in enumerate(chunks)
    ]
    # Higher relevance first; among ties, smaller chunks first so more
    # distinct pieces of the file fit in the same budget.
    order = sorted(range(len(scored)), key=lambda i: (-scored[i][2], scored[i][3]))

    budget = max(0, max_chars - len(header_text) - 100)  # slack for markers/joins
    included = set()
    used = 0
    for i in order:
        size = scored[i][3]
        if not included or used + size <= budget:
            included.add(i)
            used += size

    out_parts = [header_text] if header_text.strip() else []
    omitted_run = 0
    for i, (name, chunk_lines, score, size) in enumerate(scored):
        if i in included:
            if omitted_run:
                out_parts.append(f"# ... ({omitted_run} function/class definition(s) omitted — codebase too large to include in full) ...")
                omitted_run = 0
            out_parts.append("\n".join(chunk_lines))
        else:
            omitted_run += 1
    if omitted_run:
        out_parts.append(f"# ... ({omitted_run} function/class definition(s) omitted — codebase too large to include in full) ...")

    return "\n\n".join(p for p in out_parts if p.strip()), True


def trim_codebase(code: str, max_chars: int = 4000, problem: str = "") -> str:
    """Backward-compatible wrapper over smart_trim_codebase for call sites
    that just want the trimmed text without the was_trimmed flag."""
    trimmed, _ = smart_trim_codebase(code, max_chars, problem)
    return trimmed


def codebase_section(code: str, max_chars: int, problem: str = "") -> str:
    """Build the 'Codebase:\\n...' prompt section used by every endpoint
    that sends a codebase to the model. When smart_trim_codebase had to
    drop content, appends a short note asking the model to flag it if the
    omission affects its analysis — these endpoints stream plain text back
    (no structured 'warnings' array to attach a flag to the way
    /resolve/auto does), so the model's own response text is the only
    place this can surface for now."""
    trimmed, was_trimmed = smart_trim_codebase(code, max_chars, problem)
    note = (
        "\n\n(Note: this codebase was too large to include in full — some "
        "function/class definitions were omitted, marked with '# ... omitted ...'. "
        "If that affects your analysis, say so.)"
        if was_trimmed else ""
    )
    return "Codebase:\n" + trimmed + note

ROLE_CONTEXT = {
    "data_engineer":  "data pipelines, ETL/ELT, orchestration (Airflow/Prefect/dbt), Spark, data quality, schema design",
    "sde":            "software architecture, APIs, system design, performance, code quality, testing, CI/CD",
    "data_analyst":   "SQL queries, data models, BI tools, reporting, data accuracy, aggregations",
    "mle":            "ML pipelines, model training, feature engineering, model serving, drift detection, MLflow",
    "data_scientist": "statistical analysis, experimentation, model development, EDA, hypothesis testing",
}

class UploadRequest(BaseModel):
    content: str
    filename: str | None = None
    language: str | None = None

class AnalyzeRequest(BaseModel):
    codebase: str
    role: str
    problem: str
    user_id: str | None = None

class ResolveRequest(BaseModel):
    session_id: str
    codebase: str
    role: str
    problem: str
    diagnostic: str
    mode: str
    step_number: int = 1
    previous_steps: list = []
    override_prompt: str | None = None
    user_id: str | None = None
    issue_plan: list | None = None

class SaveSessionRequest(BaseModel):
    user_id: str
    role: str
    problem: str
    domain: str
    resolution_mode: str
    diagnostic_report: dict

class SaveStepRequest(BaseModel):
    session_id: str
    step_number: int
    ai_explanation: str
    proposed_diff: str
    user_decision: str
    override_prompt: str | None = None


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL        = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# /resolve/auto is split into two calls so each gets its own budget: fix
# analysis/explanations vs. a full regenerated file. The patched-codebase call
# gets by far the larger budget since it has to emit an entire file.
AUTO_FIXES_MAX_TOKENS = int(os.getenv("AUTO_FIXES_MAX_TOKENS", "4096"))
AUTO_PATCH_MAX_TOKENS = int(os.getenv("AUTO_PATCH_MAX_TOKENS", "8192"))
# How much of the input codebase smart_trim_codebase is allowed to keep before
# it has to start dropping whole functions/classes. Input tokens are far
# cheaper than the output budget above, so this can be generous.
AUTO_CODEBASE_MAX_CHARS = int(os.getenv("AUTO_CODEBASE_MAX_CHARS", "12000"))

async def claude_stream(messages: list, temperature: float = 0.1):
    client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs = [m for m in messages if m["role"] != "system"]
    with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        system=system,
        messages=user_msgs,
        temperature=temperature,
    ) as stream:
        for text in stream.text_stream:
            yield text

async def groq_stream(messages: list, temperature: float = 0.1):
    import asyncio
    client = _Groq(api_key=GROQ_API_KEY)
    loop = asyncio.get_event_loop()
    def _sync():
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=2048,
            temperature=temperature,
            stream=True,
        )
        chunks = []
        for chunk in completion:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                chunks.append(delta)
        return chunks
    chunks = await loop.run_in_executor(None, _sync)
    for chunk in chunks:
        yield chunk

async def ai_stream(messages: list, temperature: float = 0.1):
    provider = os.getenv("MODEL_PROVIDER", "ollama")
    if provider == "claude":
        async def _gen():
            async for chunk in claude_stream(messages, temperature):
                yield chunk
        return _gen()
    elif provider == "groq":
        async def _gen():
            async for chunk in groq_stream(messages, temperature):
                yield chunk
        return _gen()
    else:
        return ollama_stream(messages, temperature)

# Raised from the original 50KB now that smart_trim_codebase can make
# meaningful use of a larger input (whole relevant functions/classes) instead
# of the old naive head/tail/sample, which made anything past a few dozen
# lines mostly pointless to accept in the first place.
MAX_CODEBASE_SIZE = 200_000  # 200KB hard limit
MAX_REQUESTS_PER_SESSION = 20  # max steps per session

def guard_codebase(codebase: str):
    if len(codebase) > MAX_CODEBASE_SIZE:
        raise HTTPException(400, f"Codebase too large. Max {MAX_CODEBASE_SIZE//1000}KB allowed.")


def _extract_json_candidate(raw: str) -> str:
    """Drop any leading non-JSON text (markdown fences, stray commentary) before the first '{'."""
    start = raw.find("{")
    return raw[start:] if start != -1 else raw


def _scan_json_state(s: str) -> tuple[bool, int]:
    """Walk the string tracking quote/escape state and bracket depth.
    Returns (ended_inside_a_string, unclosed_bracket_depth) — both are structural
    proof of truncation regardless of what the JSON decoder's error message says."""
    depth = 0
    in_string = False
    escape = False
    for ch in s:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch in "{[":
                depth += 1
            elif ch in "}]":
                depth = max(0, depth - 1)
    return in_string, depth



# strict=False tolerates raw control characters (literal \n, \t, \r) inside
# JSON string values instead of rejecting them. When a call is asked to
# return a whole source file as a JSON string, models frequently emit a real
# newline byte instead of the two-character "\n" escape — the content is
# still exactly the code we want, just under-escaped. Without this, that
# extremely common case gets misclassified as a genuine malformed-JSON bug.
_json_decoder = json.JSONDecoder(strict=False)

def _parse_json_loose(raw: str):
    """Parse the JSON object at the start of `raw`, ignoring any trailing
    non-JSON content — e.g. a stray markdown fence the model appended despite
    being told not to. Raises json.JSONDecodeError if no valid JSON is found
    starting at the first '{'."""
    candidate = _extract_json_candidate(raw)
    obj, _end = _json_decoder.raw_decode(candidate)
    return obj

def classify_json_failure(raw: str) -> dict:
    """Determine whether an LLM response that failed to parse was truncated
    (cut off mid-token, almost always from hitting max_tokens) or is genuinely
    malformed JSON (bad escape sequences, mismatched quotes, etc — NOT raw
    control characters inside strings, which are tolerated). These need
    different handling: truncation means "ask for more budget / try again",
    malformed means "the model produced broken output despite having room to
    finish".

    Trailing content after an otherwise-complete JSON object (e.g. a stray
    markdown fence) is tolerated and still counts as valid — raw_decode only
    requires the JSON *prefix* to parse, it doesn't require the whole string
    to be clean JSON."""
    candidate = _extract_json_candidate(raw)
    try:
        _json_decoder.raw_decode(candidate)
        return {"kind": "valid"}
    except json.JSONDecodeError as exc:
        # `exc` is unbound once the except block exits (Python deletes it
        # automatically), so pull out what we need before leaving the block.
        decoder_msg = exc.msg
        decoder_pos = exc.pos

    ended_in_string, unclosed_depth = _scan_json_state(candidate)
    if ended_in_string or unclosed_depth > 0:
        reason = "mid-string" if ended_in_string else f"with {unclosed_depth} unclosed bracket(s)"
        return {
            "kind": "truncated",
            "detail": f"Response ended {reason} — the document is structurally incomplete, "
                      f"consistent with hitting a max_tokens limit rather than an escaping bug.",
            "decoder_error": decoder_msg,
            "decoder_pos": decoder_pos,
        }
    return {
        "kind": "malformed",
        "detail": f"JSON brackets are balanced (response is complete) but content is invalid: {decoder_msg}",
        "decoder_error": decoder_msg,
        "decoder_pos": decoder_pos,
    }


def sanitize_input(text: str, max_len: int = 50000) -> str:
    """Strip null bytes and limit length."""
    if not text:
        return ""
    text = text.replace("\x00", "")
    return text[:max_len]

def validate_user_id(user_id: str | None) -> bool:
    """Validate user_id is a proper UUID."""
    if not user_id:
        return False
    uuid_pattern = _re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        _re.IGNORECASE
    )
    return bool(uuid_pattern.match(user_id))

async def ollama_stream(messages: list, temperature: float = 0.1):
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature}
        }) as resp:
            async for line in resp.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                    except Exception:
                        pass

# --- Non-streaming "complete" variants -------------------------------------
# Used where we need the full response server-side before deciding what to
# send the client (e.g. to validate JSON and tell truncation apart from a
# genuine malformed-output bug). Each returns (text, stop_reason) so callers
# can use the provider's own signal for "ran out of tokens" as a second,
# stronger source of truth alongside classify_json_failure's structural scan.

async def claude_complete(messages: list, temperature: float = 0.1, max_tokens: int = 4096) -> tuple[str, str | None]:
    import asyncio
    client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs = [m for m in messages if m["role"] != "system"]
    loop = asyncio.get_event_loop()
    def _sync():
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=user_msgs,
            temperature=temperature,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return text, resp.stop_reason
    return await loop.run_in_executor(None, _sync)

async def groq_complete(messages: list, temperature: float = 0.1, max_tokens: int = 4096) -> tuple[str, str | None]:
    import asyncio
    client = _Groq(api_key=GROQ_API_KEY)
    loop = asyncio.get_event_loop()
    def _sync():
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
        )
        choice = completion.choices[0]
        return choice.message.content or "", choice.finish_reason
    return await loop.run_in_executor(None, _sync)

async def ollama_complete(messages: list, temperature: float = 0.1, max_tokens: int = 4096) -> tuple[str, str | None]:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens}
        })
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        # Ollama reports "length" when generation was cut off by num_predict.
        return text, data.get("done_reason")

async def ai_complete(messages: list, temperature: float = 0.1, max_tokens: int = 4096) -> tuple[str, str | None]:
    provider = os.getenv("MODEL_PROVIDER", "ollama")
    if provider == "claude":
        return await claude_complete(messages, temperature, max_tokens)
    elif provider == "groq":
        return await groq_complete(messages, temperature, max_tokens)
    else:
        return await ollama_complete(messages, temperature, max_tokens)

def _hit_token_limit(stop_reason: str | None) -> bool:
    # Anthropic: "max_tokens" · Groq: "length" · Ollama: "length"
    return stop_reason in ("max_tokens", "length")


def _classify_provider_error(exc: Exception) -> dict:
    """Turn a raw provider SDK exception (rate limit, auth failure, bad
    request, timeout, ...) into a clean, structured error instead of an
    unhandled 500. Discovered this was needed live: a real rate-limit
    exhaustion during testing crashed the endpoint with a raw traceback
    instead of a usable response. anthropic/groq (both OpenAI-API-style
    clients) expose a status_code attribute on their API error classes;
    fall back to the exception's class name / message when that's missing
    (e.g. network-level errors that never got a response at all)."""
    status_code = getattr(exc, "status_code", None)
    name = type(exc).__name__.lower()
    message = str(exc)
    if status_code == 429 or "ratelimit" in name:
        kind, user_message = "rate_limited", (
            "The model provider's rate limit was hit. Try again shortly, or with a smaller codebase."
        )
    elif status_code in (401, 403) or "auth" in name or "permission" in name:
        kind, user_message = "provider_auth_error", (
            "The model provider rejected the request (authentication/authorization) — check the API key configuration."
        )
    elif status_code == 400 or "badrequest" in name:
        kind, user_message = "provider_bad_request", "The model provider rejected the request as invalid."
    elif "timeout" in name or "timeout" in message.lower():
        kind, user_message = "provider_timeout", "The model provider took too long to respond. Try again."
    else:
        kind, user_message = "provider_error", "The model provider returned an unexpected error."
    return {"error": kind, "message": user_message, "provider_detail": message, "status_code": status_code}


# --- patched_codebase validation ---------------------------------------
# Deliberately static-only: this runs on LLM-generated code that may itself
# be influenced by an untrusted uploaded codebase (prompt injection), so we
# never exec()/compile-and-run it server-side. Everything here is AST/text
# analysis. It's a heuristic advisory check, not a soundness guarantee —
# findings are surfaced as warnings, never used to reject the response.

def _predominant_language(fixes: list) -> str:
    langs = [f.get("language", "").strip().lower() for f in fixes if f.get("language")]
    if not langs:
        return ""
    return _Counter(langs).most_common(1)[0][0]


def _normalize_snippet_line(line: str) -> str:
    """Strip whitespace, a trailing comma, and unify quote style — enough to
    survive the cosmetic reformatting call 2 routinely does (trailing commas
    appearing/disappearing, single vs double quotes) without losing the
    ability to tell a genuinely different line from a merely reformatted
    one."""
    line = line.strip()
    if line.endswith(","):
        line = line[:-1].rstrip()
    return line.replace("'", '"')


def _normalize_code_lines(code: str) -> set[str]:
    return {_normalize_snippet_line(l) for l in code.strip().splitlines() if l.strip()}


def _snippet_lines(snippet: str | None) -> list[str]:
    return [_normalize_snippet_line(l) for l in (snippet or "").strip().splitlines() if l.strip()]


_DISTINCTIVE_TOKEN_RE = _re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\"[^\"]*\"|'[^']*'")


def _distinctive_tokens(snippet: str) -> set[str]:
    """Identifiers and string literals from a snippet, skipping very short
    ones (control-flow keywords like 'if'/'try' carry no signal — they're
    everywhere). Used for a line-shape-independent presence check: models
    frequently write NEW control-flow code (the 'fixed' field for a fix that
    adds validation/error-handling rather than replacing broken code) as a
    squashed, colon-chained one-liner in the fix's own JSON field, while the
    actual patched_codebase properly formats the same logic across several
    indented lines — line-based comparison can't survive that reshaping, but
    the underlying identifiers and messages are unchanged either way."""
    return {t for t in _DISTINCTIVE_TOKEN_RE.findall(snippet) if len(t) > 3}


def find_unreflected_fixes(fixes: list, patched_codebase: str) -> list[str]:
    """Flag a fix whose underlying bug looks like it's still present in the
    final file.

    Checks for the bug's ABSENCE — the 'original' (broken) snippet no longer
    appearing — rather than the 'fixed' snippet's exact presence. Call 2
    legitimately renames/reformats things while restructuring (quote style,
    multi-line wrapping, a variable renamed from e.g. X_test to
    X_test_scaled as a necessary side effect of the fix), which breaks naive
    comparison against the suggested 'fixed' text even when the underlying
    bug is genuinely gone. Falls back to a looser, line-shape-independent
    token check only when a fix has no 'original' to check against — e.g. a
    fix that adds new code (validation, error handling) rather than
    replacing broken code has nothing to disprove, and its 'fixed' field is
    often a squashed, colon-chained one-liner in the JSON even though the
    real patched code correctly formats the same logic across several
    lines.

    Requires ALL of 'original's lines to still be present to call something
    "still broken", not just a majority — a multi-line 'original' commonly
    includes a line of unchanged surrounding context alongside the actual
    buggy line (e.g. the filter-setup line above a bad indexing call), and a
    majority-vote threshold flags that shared context as if the bug itself
    persisted. Requiring every line to match means even one changed line
    (almost always the fix itself) is enough to clear it."""
    if not patched_codebase.strip():
        return [f.get("title", "untitled fix") for f in fixes]

    patched_lines = _normalize_code_lines(patched_codebase)
    patched_tokens = _distinctive_tokens(patched_codebase)
    unreflected = []
    for fx in fixes:
        original_lines = _snippet_lines(fx.get("original"))
        if original_lines:
            still_broken = all(l in patched_lines for l in original_lines)
            if still_broken:
                unreflected.append(fx.get("title", "untitled fix"))
            continue

        fixed_tokens = _distinctive_tokens(fx.get("fixed") or "")
        if not fixed_tokens:
            continue
        present = sum(1 for t in fixed_tokens if t in patched_tokens)
        if present / len(fixed_tokens) < 0.6:
            unreflected.append(fx.get("title", "untitled fix"))
    return unreflected


def _unwrap_to_subscript_key(node: ast.AST) -> str | None:
    """Peel off common pandas wrapper calls/attrs (.values, .astype(...),
    .notnull(), .to_numpy(), etc.) to find an underlying df['col'] subscript,
    returning 'col' if found. Handles chains like df['x'].notnull().astype(int)."""
    while True:
        if isinstance(node, ast.Subscript):
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                return sl.value
            return None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node = node.func.value
            continue
        if isinstance(node, ast.Attribute):
            node = node.value
            continue
        return None


def find_target_leakage_features(code: str) -> list[dict]:
    """Detect a feature assigned as a direct, uncomputed copy of whatever
    column is used as the model's target/label (e.g. `df['x'] = df['label']`
    where `label` was assigned to a variable named y/target/label/labels).
    This deliberately only catches literal duplication — proxy leakage from a
    differently-named column that's merely correlated with or a consequence
    of the outcome (e.g. a field only populated after the outcome occurs)
    requires real-world domain knowledge a static check of the code can't
    derive, and isn't attempted here."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    label_columns: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & {"y", "target", "label", "labels"}:
                col = _unwrap_to_subscript_key(node.value)
                if col:
                    label_columns.add(col)

    if not label_columns:
        return []

    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Subscript):
                continue
            target_col = _unwrap_to_subscript_key(target)
            source_col = _unwrap_to_subscript_key(node.value)
            if target_col and source_col and source_col in label_columns and target_col != source_col:
                findings.append({
                    "feature": target_col,
                    "source_label_column": source_col,
                    "line": getattr(node, "lineno", None),
                })
    return findings


def _root_name_of_expr(node: ast.AST) -> str | None:
    """If node is a Name, or a chain of Subscript/Attribute access rooted at
    one (e.g. filtered['revenue'], filtered.loc), return that root name."""
    while True:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Subscript):
            node = node.value
            continue
        if isinstance(node, ast.Attribute):
            node = node.value
            continue
        return None


def _is_boolean_filter_subscript(node: ast.AST) -> bool:
    """True if node is `something[Compare(...)]` or `something[BoolOp(...)]`
    — e.g. df[df['region'] == region] or df[(a) & (b)] — which indicates row
    filtering, not column selection (df['col']) or positional slicing
    (df[1:5])."""
    return isinstance(node, ast.Subscript) and isinstance(node.slice, (ast.Compare, ast.BoolOp))


def find_positional_index_after_filter(code: str) -> list[dict]:
    """Detect an integer-literal subscript (e.g. filtered['revenue'][0]) on a
    variable that was assigned via row filtering (e.g. filtered =
    df[df['region'] == region]) anywhere in the file. Bracket indexing by an
    integer is a LABEL lookup in pandas, not a positional one — after a
    filter, surviving rows keep their original index, so label 0 may not
    exist even when the result is non-empty, causing an intermittent
    KeyError. .iloc[0] (or .loc/.at/.iat, used deliberately) is exempted —
    only bare bracket access is flagged.

    Deliberately whole-file rather than per-function-scoped, and only
    matches the exact shape above (not .query(), boolean masks built in a
    separate variable, etc.) — this is a narrower, lower-precision heuristic
    than the other checks here on purpose: whether an index is contiguous is
    a runtime property no static check can fully verify, so this errs
    toward a specific, well-understood shape rather than broad coverage."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    filtered_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_boolean_filter_subscript(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    filtered_names.add(target.id)

    if not filtered_names:
        return []

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        sl = node.slice
        if not (isinstance(sl, ast.Constant) and isinstance(sl.value, int) and not isinstance(sl.value, bool)):
            continue
        if isinstance(node.value, ast.Attribute) and node.value.attr in ("iloc", "loc", "at", "iat"):
            continue
        root = _root_name_of_expr(node.value)
        if root in filtered_names:
            findings.append({"name": root, "line": getattr(node, "lineno", None)})

    seen = set()
    deduped = []
    for f in findings:
        key = (f["name"], f["line"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


_MUTATING_METHODS = {
    "append", "extend", "insert", "remove", "pop", "clear",
    "update", "add", "discard", "sort", "reverse", "setdefault", "popitem",
}


def _param_is_mutated(param_name: str, fn_node: ast.AST) -> bool:
    """True if `param_name` is mutated anywhere in fn_node — a mutating
    method call (param.append(...)), item assignment (param[k] = v), or a
    bare augmented assignment (param += [...], which for list/dict/set
    mutates in place via __iadd__ rather than rebinding)."""
    for node in ast.walk(fn_node):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == param_name
                and node.func.attr in _MUTATING_METHODS):
            return True
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == param_name:
                    return True
        if (isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name)
                and node.target.id == param_name):
            return True
    return False


def _is_mutable_default(node: ast.AST) -> bool:
    """True for a mutable-literal default ([], {}, {1,2}) or an equivalent
    constructor call (list(), dict(), set()) — Python has no empty-set
    literal, so set() is the only way to write one, and a default value is
    evaluated exactly once at def-time either way, so a constructor call is
    just as shared/mutable as the literal form."""
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set")


def find_mutable_default_arguments(code: str) -> list[dict]:
    """Detect a function/method parameter whose default value is a mutable
    list/dict/set that's also mutated within the function body — the
    classic Python gotcha where the same default object is shared and
    mutated across every call that doesn't pass its own argument. Only
    flags parameters that are actually mutated, not merely read, so this is
    a "will misbehave" signal rather than a pure style nitpick — a mutable
    default that's never touched can't leak state."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        positional = args.posonlyargs + args.args
        paired = list(zip(positional[len(positional) - len(args.defaults):], args.defaults)) if args.defaults else []
        paired += [(p, d) for p, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]

        for param, default in paired:
            if _is_mutable_default(default) and _param_is_mutated(param.arg, node):
                findings.append({"function": node.name, "param": param.arg, "line": getattr(node, "lineno", None)})
    return findings


_PY_BUILTIN_NAMES = set(dir(_builtins)) | {"__name__", "__file__", "__doc__", "__all__", "self", "cls"}


def _direct_bind_targets(stmt: ast.AST) -> set[str]:
    """Names `stmt` binds at its OWN scope level — not names bound inside any
    nested function/class/lambda/comprehension body it contains."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {stmt.name}
    names: set[str] = set()

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            names.add(node.name)
        def visit_AsyncFunctionDef(self, node):
            names.add(node.name)
        def visit_ClassDef(self, node):
            names.add(node.name)
        def visit_Lambda(self, node):
            pass
        def visit_ListComp(self, node):
            pass
        def visit_SetComp(self, node):
            pass
        def visit_DictComp(self, node):
            pass
        def visit_GeneratorExp(self, node):
            pass
        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Store):
                names.add(node.id)
        def visit_Import(self, node):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        def visit_ImportFrom(self, node):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        def visit_ExceptHandler(self, node):
            if node.name:
                names.add(node.name)
            self.generic_visit(node)

    _Collector().visit(stmt)
    return names


def _direct_load_names(stmt: ast.AST) -> list[tuple[str, int]]:
    """Name references `stmt` reads at its OWN scope level — skips nested
    function/class/lambda/comprehension bodies (separate scopes), AND skips
    the bodies of If/For/While/With/Try (same scope, but NOT same statement:
    _collect_scope_issues already walks those bodies itself, sequentially,
    via its own recursion — scanning them again here would flatten their
    internal ordering and see a name's use before its binding purely because
    both happened to live inside the same compound statement. Only each
    compound statement's own "header" expression (the condition/iterable/
    context-manager/exception-type) is a load at this level)."""
    found: list[tuple[str, int]] = []

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            pass
        def visit_AsyncFunctionDef(self, node):
            pass
        def visit_ClassDef(self, node):
            pass
        def visit_Lambda(self, node):
            pass
        def visit_ListComp(self, node):
            pass
        def visit_SetComp(self, node):
            pass
        def visit_DictComp(self, node):
            pass
        def visit_GeneratorExp(self, node):
            pass
        def visit_If(self, node):
            self.visit(node.test)
        def visit_While(self, node):
            self.visit(node.test)
        def visit_For(self, node):
            self.visit(node.iter)
        def visit_AsyncFor(self, node):
            self.visit(node.iter)
        def visit_With(self, node):
            for item in node.items:
                self.visit(item.context_expr)
        def visit_AsyncWith(self, node):
            for item in node.items:
                self.visit(item.context_expr)
        def visit_Try(self, node):
            for handler in node.handlers:
                if handler.type:
                    self.visit(handler.type)
        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                found.append((node.id, getattr(node, "lineno", -1)))

    _Collector().visit(stmt)
    return found


def _module_level_names(tree: ast.Module) -> set[str]:
    """Everything bound directly at module top-level, or one level inside an
    if/for/while/try wrapping the top level — treated as 'eventually
    available' for nested function bodies (closures/globals resolve at call
    time, not def time, so forward references across functions are fine)."""
    names: set[str] = set()
    for stmt in tree.body:
        names |= _direct_bind_targets(stmt)
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue  # don't leak this scope's internals into "available everywhere"
        for attr in ("body", "orelse", "finalbody"):
            for sub in getattr(stmt, attr, None) or []:
                names |= _direct_bind_targets(sub)
        if isinstance(stmt, ast.Try):
            for handler in stmt.handlers:
                for sub in handler.body:
                    names |= _direct_bind_targets(sub)
    return names


def _global_nonlocal_names(fn_node: ast.AST) -> set:
    """Names this function declares via `global`/`nonlocal` anywhere in its
    own body (not inside a nested function/class, which would be a
    different scope's declaration)."""
    names: set = set()

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            pass
        def visit_AsyncFunctionDef(self, node):
            pass
        def visit_ClassDef(self, node):
            pass
        def visit_Lambda(self, node):
            pass
        def visit_Global(self, node):
            names.update(node.names)
        def visit_Nonlocal(self, node):
            names.update(node.names)

    collector = _Collector()
    for stmt in fn_node.body:
        collector.visit(stmt)
    return names


def _collect_scope_issues(body: list, outer_available: set, scope_label: str,
                           module_names: set, issues: list) -> None:
    bound: set = set()
    for stmt in body:
        for name, line in _direct_load_names(stmt):
            if name not in bound and name not in outer_available and name not in _PY_BUILTIN_NAMES:
                issues.append({"name": name, "line": line, "scope": scope_label})
        bound |= _direct_bind_targets(stmt)

        for attr in ("body", "orelse", "finalbody"):
            sub_body = getattr(stmt, attr, None)
            if sub_body and not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                _collect_scope_issues(sub_body, outer_available | bound, scope_label, module_names, issues)

        if isinstance(stmt, ast.Try):
            for handler in stmt.handlers:
                _collect_scope_issues(handler.body, outer_available | bound, scope_label, module_names, issues)

        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # A name this function assigns to ANYWHERE in its own body is a
            # local for the function's ENTIRE body, per Python's actual
            # scoping rules — even on lines before that assignment — unless
            # the function declares it `global`/`nonlocal`. Without that
            # exclusion, a name that's also bound at module level (or in an
            # enclosing function) would look available from line 1 even
            # when reading it before the local assignment is a real
            # UnboundLocalError.
            declared_global_nonlocal = _global_nonlocal_names(stmt)
            shadowed_by_local_assignment = _module_level_names(stmt) - declared_global_nonlocal
            fn_available = (outer_available | bound | module_names) - shadowed_by_local_assignment
            fn_available |= {a.arg for a in stmt.args.args} | {a.arg for a in stmt.args.kwonlyargs}
            if stmt.args.vararg:
                fn_available.add(stmt.args.vararg.arg)
            if stmt.args.kwarg:
                fn_available.add(stmt.args.kwarg.arg)
            if stmt.args.posonlyargs:
                fn_available |= {a.arg for a in stmt.args.posonlyargs}
            nested_label = f"{scope_label}.{stmt.name}" if scope_label != "<module>" else stmt.name
            _collect_scope_issues(stmt.body, fn_available, nested_label, module_names, issues)


def check_undefined_name_usage(code: str) -> list[dict]:
    """Best-effort static check for the exact failure mode a mis-applied
    'restructured' fix produces: a variable used before it's assigned at that
    point in execution (e.g. X_train referenced before train_test_split
    actually runs earlier in the same function). Never executes the code —
    heuristic only, so it can both under- and over-report on dynamic code
    (globals()/exec/star-imports); treat findings as "verify manually", not
    proof of a bug."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"kind": "syntax_error", "message": str(e), "line": e.lineno}]

    module_names = _module_level_names(tree)
    issues: list[dict] = []
    _collect_scope_issues(tree.body, set(), "<module>", module_names, issues)

    seen = set()
    deduped = []
    for issue in issues:
        key = (issue["name"], issue["scope"])
        if key not in seen:
            seen.add(key)
            deduped.append(issue)
    return deduped

@app.get("/health")
def health():
    provider = os.getenv("MODEL_PROVIDER", "ollama")
    model = GROQ_MODEL if provider == "groq" else OLLAMA_MODEL
    return {"status": "ok", "model": model, "provider": provider}

@app.post("/upload")
def upload(req: UploadRequest):
    size = len(req.content)
    if size > 500_000:
        raise HTTPException(400, "Codebase too large. Max 500KB.")
    return {
        "status": "received",
        "lines": req.content.count("\n") + 1,
        "size_kb": round(size / 1024, 1),
        "filename": req.filename,
    }

@app.post("/session/save")
def save_session(req: SaveSessionRequest):
    if not validate_user_id(req.user_id):
        raise HTTPException(400, "Invalid user ID")
    try:
        result = supabase.table("sessions").insert({
            "user_id": req.user_id,
            "role": req.role,
            "problem_statement": req.problem,
            "domain": req.domain,
            "resolution_mode": req.resolution_mode,
            "diagnostic_report": req.diagnostic_report,
            "status": "active",
        }).execute()
        return {"session_id": result.data[0]["id"]}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/session/step/save")
def save_step(req: SaveStepRequest):
    if not req.session_id or len(req.session_id) > 100:
        raise HTTPException(400, "Invalid session ID")
    try:
        supabase.table("resolution_steps").insert({
            "session_id": req.session_id,
            "step_number": req.step_number,
            "ai_explanation": req.ai_explanation,
            "proposed_diff": req.proposed_diff,
            "user_decision": req.user_decision,
            "override_prompt": req.override_prompt,
        }).execute()
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/sessions/{user_id}")
def get_sessions(user_id: str):
    try:
        result = supabase.table("sessions").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(20).execute()
        return {"sessions": result.data}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/analyze")
@limiter.limit("10/minute")
async def analyze(req: AnalyzeRequest, request: Request):
    # Try to get domain from problem text for early skill injection
    all_skills = " ".join([
        get_skill(req.role, d) for d in
        ["pipeline","schema_quality","performance","model_health","security","code_quality","environment","testing"]
        if get_skill(req.role, d)
    ])
    req.codebase = sanitize_input(req.codebase, MAX_CODEBASE_SIZE)
    req.problem = sanitize_input(req.problem, 2000)
    guard_codebase(req.codebase)
    role_skill_context = all_skills[:2000] if all_skills else ROLE_CONTEXT.get(req.role, "")

    system_prompt = (
        "You are DataVireon, an expert AI assistant for "
        + req.role.replace("_", " ")
        + " professionals.\n\n"
        + role_skill_context
        + "\n\nDomain classification guide:\n"
        "- pipeline: DAG failures, ETL errors, orchestration, task dependencies\n"
        "- schema_quality: data drift, nulls, type mismatches, duplicates, validation\n"
        "- performance: slow queries, memory, compute cost, shuffle, joins\n"
        "- model_health: model degradation, drift, training/serving skew, bias, leakage\n"
        "- security: credentials, PII, access control, encryption, compliance\n"
        "- code_quality: complexity, anti-patterns, type hints, error handling\n"
        "- environment: dependencies, Docker, infra, config, secrets\n"
        "- testing: coverage, flaky tests, CI/CD, missing tests\n\n"
        "Analyze the provided codebase and problem. Return ONLY a JSON object:\n"
        "{\"domain\":\"pipeline|schema_quality|performance|model_health|security|code_quality|environment|testing\","
        "\"severity\":\"critical|high|medium|low\","
        "\"confidence\":0.0_to_1.0,"
        "\"summary\":\"2-3 sentence plain English summary\","
        "\"symptoms\":[\"symptom1\",\"symptom2\",\"symptom3\"],"
        "\"affected_areas\":[\"area1\",\"area2\"],"
        "\"recommended_mode\":\"automatic|semi_auto|advisory\"}"
        "\nNo markdown. No text outside the JSON."
    )
    user_prompt = (
        "Role: " + req.role.replace("_", " ") + "\n"
        "Problem: " + req.problem + "\n\n"
        + codebase_section(req.codebase, 4000, req.problem)
    )
    return StreamingResponse(
        await ai_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ], temperature=0.1),
        media_type="text/plain",
    )

@app.post("/resolve/step")
@limiter.limit("20/minute")
async def resolve_step(req: ResolveRequest, request: Request):
    # Build step context
    approved_steps = [s for s in req.previous_steps if s.get("decision") == "approved"]
    fixed_count = len(approved_steps)
    steps_context = ""
    if approved_steps:
        steps_context = "\n\nAlready fixed:\n" + "\n".join(
            f"  {i+1}. {s.get('explanation','')[:100]}"
            for i, s in enumerate(approved_steps)
        )

    override = ("\n\nUser instruction: " + req.override_prompt) if req.override_prompt else ""

    # Use issue plan for precise issue tracking
    issue_instruction = ""
    issue_plan = getattr(req, "issue_plan", None)
    if issue_plan and len(issue_plan) > 0:
        current_idx = fixed_count
        if current_idx < len(issue_plan):
            current_issue = issue_plan[current_idx]
            issue_instruction = (
                f"\n\nYOU MUST FIX THIS SPECIFIC ISSUE ONLY (#{current_idx+1} of {len(issue_plan)}):\n"
                f"  Title: {current_issue.get('title','')}\n"
                f"  Severity: {current_issue.get('severity','')}\n"
                f"  Description: {current_issue.get('description','')}\n"
                f"  Location: {current_issue.get('location','')}\n"
                f"Do NOT fix anything else. Do NOT repeat previous fixes.\n"
                f"Set is_final=true if this is issue #{len(issue_plan)} (the last one).\n"
            )
        else:
            issue_instruction = "\nAll issues have been fixed. Set is_final=true.\n"

    system_prompt = (
        "You are DataVireon, an expert code resolution assistant in semi-automatic mode.\n"
        "Provide ONE focused fix step for the specific issue instructed. Return ONLY JSON:\n"
        "{\"step_title\":\"short specific title\","
        "\"explanation\":\"clear explanation of what and why\","
        "\"diff\":\"corrected code — use \\n for newlines inside JSON strings\","
        "\"language\":\"python|sql|yaml|etc\","
        "\"is_final\":true_or_false}"
        "\nNo markdown. No text outside the JSON."
        "\nCRITICAL: Never repeat a fix that was already applied."
    )
    user_prompt = (
        "Role: " + req.role.replace("_", " ") + "\n"
        "Problem: " + req.problem + "\n"
        "Diagnostic: " + req.diagnostic + "\n"
        "Step number: " + str(req.step_number)
        + steps_context + issue_instruction + override + "\n\n"
        + codebase_section(req.codebase, 3000, req.problem) + "\n\n"
        "Provide the fix for the specific issue instructed above."
    )
    return StreamingResponse(
        await ai_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ], temperature=0.2),
        media_type="text/plain",
    )

@app.get("/session/{session_id}/steps")
def get_steps(session_id: str):
    try:
        result = supabase.table("resolution_steps").select("*").eq("session_id", session_id).order("step_number").execute()
        return {"steps": result.data}
    except Exception as e:
        raise HTTPException(500, str(e))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

class RepoRequest(BaseModel):
    repo_url: str

class RepoFilesRequest(BaseModel):
    repo_url: str
    file_paths: list[str]

def parse_repo_url(url: str) -> tuple[str, str]:
    # Handle formats:
    # https://github.com/owner/repo
    # github.com/owner/repo
    # owner/repo
    url = url.strip().rstrip("/")
    url = url.replace("https://github.com/", "")
    url = url.replace("http://github.com/", "")
    url = url.replace("github.com/", "")
    parts = url.split("/")
    if len(parts) < 2:
        raise ValueError("Invalid GitHub URL")
    return parts[0], parts[1]

@app.post("/github/tree")
async def get_repo_tree(req: RepoRequest):
    try:
        owner, repo = parse_repo_url(req.repo_url)
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        async with httpx.AsyncClient(timeout=30) as client:
            # Get default branch
            repo_res = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=headers
            )
            if repo_res.status_code != 200:
                raise HTTPException(404, f"Repo not found: {owner}/{repo}")
            
            default_branch = repo_res.json().get("default_branch", "main")
            
            # Get file tree
            tree_res = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
                headers=headers
            )
            tree_data = tree_res.json()
            
            # Filter to relevant files only
            relevant_extensions = {
                ".py", ".sql", ".yaml", ".yml", ".json", ".ts", ".tsx",
                ".js", ".jsx", ".tf", ".dockerfile", ".sh", ".toml",
                ".cfg", ".ini", ".env.example", ".md"
            }
            
            files = []
            for item in tree_data.get("tree", []):
                if item["type"] == "blob":
                    path = item["path"]
                    ext = "." + path.split(".")[-1] if "." in path else ""
                    # Skip common non-code dirs
                    skip = any(path.startswith(p) for p in [
                        "node_modules/", ".git/", "__pycache__/",
                        ".next/", "dist/", "build/", ".venv/", "venv/"
                    ])
                    if not skip and (ext.lower() in relevant_extensions or "dockerfile" in path.lower()):
                        files.append({
                            "path": path,
                            "size": item.get("size", 0),
                            "type": ext.lstrip(".")
                        })
            
            return {
                "owner": owner,
                "repo": repo,
                "branch": default_branch,
                "files": files[:200]  # Cap at 200 files
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/github/contents")
async def get_file_contents(req: RepoFilesRequest):
    try:
        owner, repo = parse_repo_url(req.repo_url)
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        contents = []
        total_size = 0
        
        async with httpx.AsyncClient(timeout=30) as client:
            for path in req.file_paths[:10]:  # Cap at 10 files
                res = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                    headers=headers
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("encoding") == "base64":
                        import base64
                        decoded = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                        if total_size + len(decoded) < 50000:  # 50KB total cap
                            contents.append({
                                "path": path,
                                "content": decoded,
                                "size": len(decoded)
                            })
                            total_size += len(decoded)
        
        combined = "\n\n".join([
            f"# File: {f['path']}\n{f['content']}"
            for f in contents
        ])
        
        return {
            "files": contents,
            "combined": combined,
            "total_size_kb": round(total_size / 1024, 1)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

class AdvisoryRequest(BaseModel):
    codebase: str
    role: str
    problem: str
    diagnostic: dict

@app.post("/advisory")
@limiter.limit("10/minute")
async def advisory(req: AdvisoryRequest, request: Request):
    skill_prompt = get_skill(req.role, req.diagnostic.get("domain", ""))

    system_prompt = (
        (skill_prompt + "\n\n") if skill_prompt else ""
    ) + (
        "You are DataVireon in advisory mode. Do NOT make code changes.\n"
        "Provide a prioritised list of recommendations.\n"
        "Return ONLY JSON:\n"
        '{"recommendations":['
        '{"priority":1,'
        '"title":"short title",'
        '"severity":"critical|high|medium|low",'
        '"explanation":"detailed explanation",'
        '"effort":"low|medium|high",'
        '"action":"exact steps to fix this"}],'
        '"summary":"overall assessment",'
        '"quick_wins":["thing you can fix in 5 mins"]}'
        "\nNo markdown. No text outside JSON. Include 3-6 recommendations."
    )
    user_prompt = (
        "Role: " + req.role.replace("_", " ") + "\n"
        "Problem: " + req.problem + "\n"
        "Diagnostic: " + json.dumps(req.diagnostic) + "\n\n"
        + codebase_section(req.codebase, 4000, req.problem)
    )
    return StreamingResponse(
        await ai_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.2),
        media_type="text/plain",
    )

class AutoResolveRequest(BaseModel):
    codebase: str
    role: str
    problem: str
    diagnostic: dict
    user_id: str | None = None
    session_id: str | None = None

@app.post("/resolve/auto")
@limiter.limit("5/minute")
async def resolve_auto(req: AutoResolveRequest, request: Request):
    # /analyze already guards its own input, but /resolve/auto can be
    # (and, via direct API access rather than the normal UI flow, has been)
    # called on its own — it should enforce the same size ceiling rather
    # than relying on a different endpoint to have done it first.
    guard_codebase(req.codebase)

    # A holistic "find ALL issues" audit shouldn't be scoped to a single
    # domain's checklist — /analyze's domain classification is a best guess
    # from a trimmed excerpt, and gating on just that one domain (e.g.
    # "code_quality") silently drops known-issues checklists that live under
    # other domains (e.g. "model_health"'s leakage/div-by-zero patterns),
    # even though the general instructions below ask for those issues too.
    # Combine all domains' skills, same as /analyze already does.
    all_skills = " ".join([
        get_skill(req.role, d) for d in
        ["pipeline", "schema_quality", "performance", "model_health", "security", "code_quality", "environment", "testing"]
        if get_skill(req.role, d)
    ])
    skill_prompt = all_skills[:2500] if all_skills else ROLE_CONTEXT.get(req.role, "")
    # Input tokens are cheap relative to the output budget (AUTO_PATCH_MAX_TOKENS is
    # already 8192) — the old 3000-char limit was never actually necessitated by the
    # model's context window (131K tokens on Groq's llama-3.3-70b-versatile), it just
    # meant any realistically-sized file got sliced into scattered, incoherent
    # fragments that could (and empirically did, in testing) skip the actual buggy
    # function entirely. Structural + relevance-aware trimming makes far better use
    # of a larger budget than the old sampling did of the smaller one.
    trimmed_codebase, codebase_was_trimmed = smart_trim_codebase(
        req.codebase, AUTO_CODEBASE_MAX_CHARS, problem=req.problem
    )

    # --- Call 1: diagnose + explain fixes (no patched_codebase in this call at all) ---
    fixes_system_prompt = (
        (skill_prompt + "\n\n") if skill_prompt else ""
    ) + (
        "You are DataVireon in fully automatic resolution mode (step 1 of 2: diagnosis).\n"
        "Analyze the entire codebase holistically — including control flow and "
        "variable lifetime across functions — before proposing any fix. "
        "Identify ALL issues: syntax errors, runtime errors, logic bugs, "
        "data leakage, incorrect metrics, and structural/ordering problems. "
        "Look specifically for: (a) target leakage — a feature that duplicates "
        "the label outright, or is only ever populated as a consequence of the "
        "very outcome being predicted; (b) any scaler/imputer/encoder being fit "
        "(via .fit or .fit_transform) on more than one of train/validation/test/"
        "production data — it must be fit exactly once, on training data only; "
        "(c) unguarded division in hand-rolled metric calculations that can hit "
        "a zero denominator; (d) label/bracket-based indexing (e.g. series[0]) "
        "on a pandas Series/DataFrame that was produced by filtering, "
        "splitting, or sorting — this looks up index LABEL 0, not position 0, "
        "and raises KeyError whenever row 0 didn't survive that operation even "
        "though the result is non-empty; only .iloc[0] is guaranteed to mean "
        "\"the first row of whatever remains.\" A not-empty check alone does "
        "NOT fix this — it must actually switch to .iloc.\n"
        "\n"
        "If a correct fix requires reordering logic, merging functions, or "
        "changing the sequence of operations (e.g. splitting data before "
        "fitting a transformer, not after), say so precisely in 'explanation' — "
        "name the function(s) and exactly where the reordering must happen. "
        "This description will be handed to a second step that rewrites the "
        "full file, so it must be exact. Set 'restructured': true on that fix.\n"
        "\n"
        "Classify severity as 'blocking' (prevents execution: syntax errors, "
        "NameError, invalid arguments) or 'logic' (runs but produces "
        "wrong/misleading results: leakage, wrong metric, wrong split).\n"
        "\n"
        "Before writing 'explanation', re-check it against the actual "
        "'original'/'fixed' snippets: state the specific mechanism that's "
        "wrong (which variable holds a stale/wrong value, which collection "
        "vs. which index, which check is missing) rather than a generic-"
        "sounding justification that doesn't match what the snippets show. "
        "E.g. if the bug is indexing into the wrong collection, say that — "
        "don't default to 'this would raise an error on empty input' unless "
        "the code you're changing is actually missing that check.\n"
        "\n"
        "Return ONLY JSON:\n"
        '{"fixes":['
        '{"title":"fix title",'
        '"severity":"blocking|logic",'
        '"restructured":true|false,'
        '"explanation":"what was wrong, why this fixes it, and — if restructured — exactly where/how the code must be reordered",'
        '"original":"original code snippet",'
        '"fixed":"corrected code snippet",'
        '"language":"python|sql|yaml|etc"}],'
        '"summary":"overall summary of all changes made",'
        '"warnings":["any caveats, assumptions, or things to verify manually"]}'
        "\nDo NOT include a patched_codebase field — that is generated in a separate step."
        "\nNo markdown. No text outside JSON."
    )
    fixes_user_prompt = (
        "Role: " + req.role.replace("_", " ") + "\n"
        "Problem: " + req.problem + "\n"
        "Diagnostic: " + json.dumps(req.diagnostic) + "\n\n"
        "Codebase:\n" + trimmed_codebase + "\n\n"
        "Identify and explain all necessary fixes."
    )
    try:
        fixes_text, fixes_stop = await ai_complete(
            [
                {"role": "system", "content": fixes_system_prompt},
                {"role": "user", "content": fixes_user_prompt},
            ],
            temperature=0.1,
            max_tokens=AUTO_FIXES_MAX_TOKENS,
        )
    except HTTPException:
        raise
    except Exception as e:
        info = _classify_provider_error(e)
        logger.error("resolve_auto[fixes]: provider error: %s", info["provider_detail"])
        raise HTTPException(502, detail={**info, "stage": "fixes"})

    fixes_check = classify_json_failure(fixes_text)
    if fixes_check["kind"] != "valid":
        if fixes_check["kind"] == "truncated" or _hit_token_limit(fixes_stop):
            logger.warning(
                "resolve_auto[fixes]: truncated (stop_reason=%s, chars=%d): %s",
                fixes_stop, len(fixes_text), fixes_check.get("detail"),
            )
            raise HTTPException(502, detail={
                "error": "truncated_response",
                "stage": "fixes",
                "message": "The fix analysis was cut off before finishing (hit the token limit). "
                           "Try again, or with a smaller codebase.",
                "stop_reason": fixes_stop,
            })
        logger.error("resolve_auto[fixes]: malformed JSON: %s", fixes_check.get("detail"))
        raise HTTPException(502, detail={
            "error": "malformed_json",
            "stage": "fixes",
            "message": f"The model returned invalid JSON: {fixes_check['detail']}",
        })
    fixes_data = _parse_json_loose(fixes_text)

    # --- Call 2: given the fixes above, regenerate the full patched file ---
    # Only pass what call 2 needs to decide WHAT to do and WHY — not the
    # original/fixed snippets, which were for the human-facing fix cards and
    # are redundant here: call 2 already gets the complete original file
    # below, so re-embedding isolated before/after lines just inflates this
    # prompt without adding information, eating into the budget available
    # for the actual output (the full regenerated file).
    condensed_fixes = [
        {k: v for k, v in fx.items() if k in ("title", "severity", "restructured", "explanation", "language")}
        for fx in fixes_data.get("fixes", [])
    ]
    patch_system_prompt = (
        "You are DataVireon in fully automatic resolution mode (step 2 of 2: patched file).\n"
        "The following fixes were already identified for this codebase — apply ALL of "
        "them together so the result is a single coherent, runnable program:\n"
        + json.dumps(condensed_fixes) + "\n\n"
        "CRITICAL CONSTRAINT:\n"
        "1. Trace the execution order of the patched code mentally, top to bottom.\n"
        "2. For every variable used, confirm it is defined and in scope at that "
        "point in the patched flow — not just in isolation.\n"
        "3. Where a fix above has 'restructured': true, actually move/reorder that "
        "logic in the file — do not just patch the isolated snippet in place.\n"
        "4. The output must be the complete file, self-consistent, and runnable "
        "end-to-end — never a concatenation of independently valid but mutually "
        "incompatible snippets.\n"
        "5. When moving preprocessing after a train/test split, do not simply "
        "call the same fit_transform-based helper on each split separately — "
        "that re-fits a new scaler/imputer/encoder on the test data instead of "
        "reusing the one fit on training data, which is itself a leakage-"
        "adjacent bug. Fit each transformer exactly once, on the training data, "
        "then apply it to every other split with .transform() only.\n"
        "6. When fixing a KeyError/IndexError on a filtered/split/sorted "
        "Series or DataFrame, an emptiness check alone is not sufficient — "
        "series[0] looks up index label 0, which may not exist even when the "
        "result is non-empty. Switch to .iloc[0] for positional access; only "
        "add the emptiness check on top of that if the collection can "
        "legitimately be empty.\n"
        "\n"
        "Return ONLY JSON:\n"
        '{"patched_codebase":"the complete fixed codebase, verified to run end-to-end",'
        '"warnings":["any additional caveats from applying these fixes together"]}'
        "\nNo markdown. No text outside JSON."
    )
    patch_user_prompt = (
        "Codebase:\n" + trimmed_codebase + "\n\n"
        "Apply all the fixes listed above and return the complete patched codebase."
    )
    try:
        patch_text, patch_stop = await ai_complete(
            [
                {"role": "system", "content": patch_system_prompt},
                {"role": "user", "content": patch_user_prompt},
            ],
            temperature=0.1,
            max_tokens=AUTO_PATCH_MAX_TOKENS,
        )
    except HTTPException:
        raise
    except Exception as e:
        info = _classify_provider_error(e)
        logger.error("resolve_auto[patch]: provider error: %s", info["provider_detail"])
        # Call 1 already succeeded — don't throw that work away.
        raise HTTPException(502, detail={
            **info, "stage": "patch",
            "fixes": fixes_data.get("fixes", []),
            "summary": fixes_data.get("summary", ""),
        })

    patch_check = classify_json_failure(patch_text)
    if patch_check["kind"] != "valid":
        # Call 1 already succeeded — don't throw that work away.
        partial = {
            "fixes": fixes_data.get("fixes", []),
            "summary": fixes_data.get("summary", ""),
        }
        if patch_check["kind"] == "truncated" or _hit_token_limit(patch_stop):
            logger.warning(
                "resolve_auto[patch]: truncated (stop_reason=%s, chars=%d): %s",
                patch_stop, len(patch_text), patch_check.get("detail"),
            )
            raise HTTPException(502, detail={
                "error": "truncated_response",
                "stage": "patch",
                "message": "The patched codebase was cut off before finishing (hit the token limit). "
                           "The fixes above are valid — try re-running, or reduce codebase size.",
                "stop_reason": patch_stop,
                **partial,
            })
        logger.error("resolve_auto[patch]: malformed JSON: %s", patch_check.get("detail"))
        raise HTTPException(502, detail={
            "error": "malformed_json",
            "stage": "patch",
            "message": f"The model returned invalid JSON for the patched codebase: {patch_check['detail']}",
            **partial,
        })
    patch_data = _parse_json_loose(patch_text)
    fixes_list = fixes_data.get("fixes", [])
    patched_code = patch_data.get("patched_codebase", "")

    # --- Validate: does patched_codebase actually reflect the claimed fixes,
    # and does it look like it'll run without a NameError from ordering? ---
    validation_warnings: list[str] = []

    if codebase_was_trimmed:
        validation_warnings.append(
            "Validation: the submitted codebase was too large to analyze in full — some "
            "function/class definitions were omitted (see the '# ... omitted ...' marker "
            "in what was analyzed). This diagnosis and patch only cover the portions shown; "
            "review the rest manually."
        )
        logger.warning("resolve_auto[validate]: codebase was trimmed before analysis")

    unreflected = find_unreflected_fixes(fixes_list, patched_code)
    if unreflected:
        validation_warnings.append(
            "Validation: the patched codebase doesn't clearly contain the fix for: "
            + "; ".join(unreflected) + ". The rewrite step may not have applied it — review manually."
        )
        logger.warning("resolve_auto[validate]: %d fix(es) not reflected in patched_codebase: %s",
                        len(unreflected), unreflected)

    if _predominant_language(fixes_list) == "python" and patched_code.strip():
        name_issues = check_undefined_name_usage(patched_code)
        for issue in name_issues:
            if issue.get("kind") == "syntax_error":
                validation_warnings.append(
                    f"Validation: patched_codebase has a Python syntax error at line {issue.get('line')}: {issue.get('message')}"
                )
            else:
                validation_warnings.append(
                    f"Validation: '{issue['name']}' is used in {issue['scope']} (line {issue['line']}) "
                    f"before it's clearly defined there — possible NameError if a restructured fix "
                    f"wasn't fully applied. Verify manually."
                )
        if name_issues:
            logger.warning("resolve_auto[validate]: %d potential undefined-name issue(s) in patched_codebase",
                            len(name_issues))

        leakage_findings = find_target_leakage_features(patched_code)
        for finding in leakage_findings:
            validation_warnings.append(
                f"Validation: feature '{finding['feature']}' (line {finding['line']}) is a direct, "
                f"uncomputed copy of '{finding['source_label_column']}', which is used as the model's "
                f"target — this is target leakage and will inflate reported accuracy. Remove it as a feature."
            )
        if leakage_findings:
            logger.warning("resolve_auto[validate]: %d target-leakage feature(s) still in patched_codebase",
                            len(leakage_findings))

        index_findings = find_positional_index_after_filter(patched_code)
        for finding in index_findings:
            validation_warnings.append(
                f"Validation: '{finding['name']}' (line {finding['line']}) was assigned from a row filter "
                f"and is then indexed with a plain integer — that's a label lookup, not positional, and can "
                f"raise KeyError even when the filtered result is non-empty. Use .iloc[...] instead."
            )
        if index_findings:
            logger.warning("resolve_auto[validate]: %d label-vs-positional indexing issue(s) in patched_codebase",
                            len(index_findings))

        mutable_default_findings = find_mutable_default_arguments(patched_code)
        for finding in mutable_default_findings:
            validation_warnings.append(
                f"Validation: '{finding['param']}' in {finding['function']} (line {finding['line']}) defaults "
                f"to a mutable list/dict/set and is mutated in the function body — that default is shared "
                f"and accumulates across every call that doesn't pass its own argument. "
                f"Use None as the default and create the mutable value inside the function instead."
            )
        if mutable_default_findings:
            logger.warning("resolve_auto[validate]: %d mutable-default-argument issue(s) in patched_codebase",
                            len(mutable_default_findings))

    return {
        "fixes": fixes_list,
        "summary": fixes_data.get("summary", ""),
        "warnings": (fixes_data.get("warnings") or []) + (patch_data.get("warnings") or []) + validation_warnings,
        "patched_codebase": patched_code,
    }

class SchemaAnalyzeRequest(BaseModel):
    supabase_url: str
    supabase_key: str
    role: str
    problem: str | None = None

@app.post("/analyze/schema")
async def analyze_schema(req: SchemaAnalyzeRequest):
    if not req.supabase_url.startswith("https://") or "supabase.co" not in req.supabase_url:
        raise HTTPException(400, "Invalid Supabase URL")
    req.problem = sanitize_input(req.problem or "", 2000)

    headers = {
        "apikey": req.supabase_key,
        "Authorization": f"Bearer {req.supabase_key}",
        "Content-Type": "application/json"
    }

    common_tables = [
        "users","profiles","sessions","orders","products","customers",
        "workspaces","codebase_uploads","resolution_steps","transactions",
        "events","logs","messages","notifications","settings","teams",
        "projects","tasks","comments","files","reports","analytics"
    ]

    schema_info = ""
    found_tables = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for table in common_tables:
                res = await client.get(
                    f"{req.supabase_url}/rest/v1/{table}?select=*&limit=0",
                    headers=headers
                )
                if res.status_code == 200:
                    found_tables.append(table)

            if not found_tables:
                raise HTTPException(400, "No accessible tables found. Check your URL and anon key.")

            for table in found_tables[:8]:
                res = await client.get(
                    f"{req.supabase_url}/rest/v1/{table}?select=*&limit=1",
                    headers=headers
                )
                schema_info += f"Table: {table}\n"
                if res.status_code == 200:
                    data = res.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        row = data[0]
                        for col, val in row.items():
                            col_type = type(val).__name__ if val is not None else "unknown/nullable"
                            nullable = "nullable" if val is None else "has_value"
                            schema_info += f"  - {col}: {col_type} ({nullable})\n"
                    else:
                        schema_info += f"  (empty table — cannot infer column types)\n"

                    # Get row count
                    count_res = await client.get(
                        f"{req.supabase_url}/rest/v1/{table}?select=count",
                        headers={**headers, "Prefer": "count=exact"}
                    )
                    if "content-range" in count_res.headers:
                        total = count_res.headers["content-range"].split("/")[-1]
                        schema_info += f"  Row count: {total}\n"

                    # Check for common missing columns based on role
                    cols = list(data[0].keys()) if data and isinstance(data, list) and data else []
                    missing = []
                    if req.role == "data_engineer":
                        for expected in ["created_at","updated_at","deleted_at","batch_id","source"]:
                            if expected not in cols:
                                missing.append(expected)
                    elif req.role == "mle":
                        for expected in ["label","feature_version","split","created_at"]:
                            if expected not in cols:
                                missing.append(expected)
                    elif req.role == "data_analyst":
                        for expected in ["created_at","updated_at","status","category"]:
                            if expected not in cols:
                                missing.append(expected)
                    elif req.role == "sde":
                        for expected in ["created_at","updated_at","user_id","deleted_at"]:
                            if expected not in cols:
                                missing.append(expected)
                    elif req.role == "data_scientist":
                        for expected in ["created_at","experiment_id","variant","outcome"]:
                            if expected not in cols:
                                missing.append(expected)
                    if missing:
                        schema_info += f"  Missing expected columns for {req.role}: {', '.join(missing)}\n"

                schema_info += "\n"

            schema_info = f"Role context: {req.role.replace('_',' ')}\nAccessible tables: {', '.join(found_tables)}\n\n" + schema_info

    except httpx.TimeoutException:
        raise HTTPException(408, "Connection timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Schema fetch failed: {str(e)}")

    skill_prompt = get_skill(req.role, "schema_quality")
    role_focus = {
        "data_engineer": "Focus on: missing audit columns (created_at, updated_at, batch_id), data lineage gaps, partitioning opportunities, ingestion patterns, and pipeline reliability.",
        "sde": "Focus on: missing soft delete columns, lack of user_id foreign keys, RLS gaps, missing indexes on frequently queried columns, and API design patterns.",
        "data_analyst": "Focus on: missing date dimensions, lack of status/category columns, aggregation opportunities, missing fact/dimension table patterns, and reporting query performance.",
        "mle": "Focus on: missing label columns, lack of feature versioning, no experiment tracking columns, training data quality issues, and label imbalance indicators.",
        "data_scientist": "Focus on: missing experiment_id, variant, outcome columns, lack of temporal tracking, statistical validity of the data structure, and A/B testing infrastructure.",
    }

    system_prompt = (
        (skill_prompt + "\n\n") if skill_prompt else ""
    ) + (
        f"You are DataVireon analyzing a live Supabase database schema for a {req.role.replace('_',' ')} professional.\n"
        f"{role_focus.get(req.role, '')}\n\n"
        "Identify schema quality issues, missing constraints, security gaps, and role-specific optimization opportunities.\n"
        "Return ONLY JSON:\n"
        "{\"domain\":\"schema_quality\","
        "\"severity\":\"critical|high|medium|low\","
        "\"confidence\":0.0_to_1.0,"
        "\"summary\":\"2-3 sentence role-specific summary\","
        "\"symptoms\":[\"specific issue 1\",\"specific issue 2\",\"specific issue 3\"],"
        "\"affected_areas\":[\"table1\",\"table2\"],"
        "\"recommended_mode\":\"advisory\"}"
        "\nNo markdown. No text outside JSON."
    )
    user_prompt = (
        f"Role: {req.role.replace('_', ' ')}\n"
        f"Problem: {req.problem or 'Analyze this schema for quality issues'}\n\n"
        f"Schema:\n{schema_info[:6000]}"
    )
    return StreamingResponse(
        await ai_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.1),
        media_type="text/plain",
    )

class RunbookRequest(BaseModel):
    role: str
    problem: str
    diagnostic: dict
    steps: list

@app.post("/runbook")
async def generate_runbook(req: RunbookRequest):
    skill_prompt = get_skill(req.role, req.diagnostic.get("domain", ""))
    system_prompt = (
        "You are DataVireon. Generate a professional incident runbook in markdown.\n"
        "Include these sections:\n"
        "# Incident Runbook\n"
        "## Problem Summary\n"
        "## Root Cause\n"
        "## Resolution Steps\n"
        "## Prevention\n"
        "## References\n"
        "Be concise and actionable. Use code blocks for code snippets."
    )
    steps_text = "\n".join(
        f"Step {s.get('step_number', i+1)}: {s.get('explanation', '')} — {s.get('decision', '')}"
        for i, s in enumerate(req.steps)
    )
    user_prompt = (
        f"Role: {req.role.replace('_', ' ')}\n"
        f"Problem: {req.problem}\n"
        f"Diagnostic: {json.dumps(req.diagnostic)}\n"
        f"Resolution steps taken:\n{steps_text}"
    )
    return StreamingResponse(
        await ai_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.2),
        media_type="text/plain",
    )

class PlanRequest(BaseModel):
    codebase: str
    role: str
    problem: str
    diagnostic: dict

@app.post("/resolve/plan")
async def resolve_plan(req: PlanRequest):
    skill_prompt = get_skill(req.role, req.diagnostic.get("domain", ""))

    system_prompt = (
        (skill_prompt + "\n\n") if skill_prompt else ""
    ) + (
        "You are DataVireon doing a comprehensive code audit.\n"
        "Your job is to identify EVERY issue in the codebase — be exhaustive and aggressive.\n"
        "Do not miss anything. Look for:\n"
        "- Security vulnerabilities (injection, auth, secrets, permissions)\n"
        "- Performance issues (N+1, missing indexes, inefficient algorithms)\n"
        "- Data quality issues (missing validation, type errors, nulls)\n"
        "- Code quality (hardcoded values, missing error handling, logging)\n"
        "- Production readiness (debug mode, missing monitoring, no rate limiting)\n"
        "- Best practice violations (plaintext passwords, no hashing, missing CSRF)\n"
        "Return ONLY JSON:\n"
        "{\"total_issues\": N,\n"
        "\"issues\": [\n"
        "{\"id\": 1, \"severity\": \"critical|high|medium|low\", "
        "\"title\": \"short title\", "
        "\"description\": \"what is wrong and why it matters\", "
        "\"location\": \"which function/line/area\"}\n"
        "],\n"
        "\"fix_order\": [1,2,3...] // ordered by priority}\n"
        "Be exhaustive. Find ALL issues. Minimum 5 issues for any production code."
    )
    user_prompt = (
        f"Role: {req.role.replace('_', ' ')}\n"
        f"Problem: {req.problem}\n"
        f"Diagnostic: {json.dumps(req.diagnostic)}\n\n"
        + codebase_section(req.codebase.replace("\x00", ""), 6000, req.problem)
    )
    return StreamingResponse(
        await ai_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.1),
        media_type="text/plain",
    )

class FeedbackRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    rating: int  # 1 or -1
    diagnostic_quality: int | None = None
    resolution_quality: int | None = None
    comment: str | None = None
    role: str | None = None
    domain: str | None = None
    problem: str | None = None
    codebase_snippet: str | None = None
    diagnostic_summary: str | None = None

@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    try:
        data = {
            "rating": req.rating,
            "role": req.role,
            "domain": req.domain,
            "problem": sanitize_input(req.problem or "", 500),
            "codebase_snippet": sanitize_input(req.codebase_snippet or "", 1000),
            "diagnostic_summary": sanitize_input(req.diagnostic_summary or "", 500),
            "comment": sanitize_input(req.comment or "", 1000),
        }
        if req.session_id and validate_user_id(req.session_id):
            data["session_id"] = req.session_id
        if req.user_id and validate_user_id(req.user_id):
            data["user_id"] = req.user_id
        if req.diagnostic_quality:
            data["diagnostic_quality"] = req.diagnostic_quality
        if req.resolution_quality:
            data["resolution_quality"] = req.resolution_quality

        supabase.table("feedback").insert(data).execute()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, f"Feedback failed: {str(e)}")


class FewShotRequest(BaseModel):
    role: str
    domain: str
    problem_summary: str
    codebase_snippet: str
    diagnostic_summary: str
    resolution_steps: list

@app.post("/few-shot/save")
async def save_few_shot(req: FewShotRequest):
    try:
        # Check if similar example exists (same role + domain)
        existing = supabase.table("few_shot_examples")\
            .select("id, upvotes, problem_summary")\
            .eq("role", req.role)\
            .eq("domain", req.domain)\
            .limit(5)\
            .execute()

        # Simple similarity check — if problem summary overlaps significantly
        for ex in (existing.data or []):
            overlap = len(set(req.problem_summary.lower().split()) &
                         set(ex["problem_summary"].lower().split()))
            if overlap > 5:
                # Upvote existing instead of creating duplicate
                supabase.table("few_shot_examples")\
                    .update({"upvotes": ex["upvotes"] + 1})\
                    .eq("id", ex["id"])\
                    .execute()
                return {"status": "upvoted", "id": ex["id"]}

        # Save new example
        result = supabase.table("few_shot_examples").insert({
            "role": req.role,
            "domain": req.domain,
            "problem_summary": sanitize_input(req.problem_summary, 500),
            "codebase_snippet": sanitize_input(req.codebase_snippet, 2000),
            "diagnostic_summary": sanitize_input(req.diagnostic_summary, 500),
            "resolution_steps": req.resolution_steps,
        }).execute()
        return {"status": "saved", "id": result.data[0]["id"]}
    except Exception as e:
        raise HTTPException(500, f"Few-shot save failed: {str(e)}")


@app.get("/few-shot/{role}/{domain}")
async def get_few_shots(role: str, domain: str):
    try:
        result = supabase.table("few_shot_examples")\
            .select("problem_summary, diagnostic_summary, resolution_steps, upvotes")\
            .eq("role", role)\
            .eq("domain", domain)\
            .order("upvotes", desc=True)\
            .limit(2)\
            .execute()
        return {"examples": result.data or []}
    except Exception as e:
        return {"examples": []}
