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
import httpx, os, json, logging, ast, builtins as _builtins
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

def trim_codebase(code: str, max_chars: int = 4000) -> str:
    """Trim codebase intelligently — keep imports and function signatures."""
    if len(code) <= max_chars:
        return code
    lines = code.split("\n")
    # Always keep first 20 lines (imports) and last 20 lines
    head = lines[:20]
    tail = lines[-20:]
    middle = lines[20:-20]
    # Sample middle evenly
    if middle:
        step = max(1, len(middle) // 20)
        middle = middle[::step][:20]
    trimmed = "\n".join(head + ["# ... (trimmed for context) ..."] + middle + tail)
    return trimmed[:max_chars]

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

MAX_CODEBASE_SIZE = 50_000  # 50KB hard limit
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


import re as _re

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


def _normalize_code_lines(code: str) -> set[str]:
    return {line.strip() for line in code.strip().splitlines() if line.strip()}


def find_unreflected_fixes(fixes: list, patched_codebase: str) -> list[str]:
    """Check whether each claimed fix actually shows up in the final file.
    Catches the case where the diagnosis (call 1) is fine but the rewrite
    (call 2) silently dropped or ignored one of the fixes."""
    if not patched_codebase.strip():
        return [f.get("title", "untitled fix") for f in fixes]
    patched_lines = _normalize_code_lines(patched_codebase)
    missing = []
    for fx in fixes:
        fixed_snippet = (fx.get("fixed") or "").strip()
        if not fixed_snippet:
            continue
        snippet_lines = [l.strip() for l in fixed_snippet.splitlines() if l.strip()]
        if not snippet_lines:
            continue
        present = sum(1 for l in snippet_lines if l in patched_lines)
        if present / len(snippet_lines) < 0.5:
            missing.append(fx.get("title", "untitled fix"))
    return missing


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
    function/class/lambda/comprehension bodies, which are checked as their
    own separate scopes."""
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
            fn_available = outer_available | bound | module_names
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
    req.codebase = sanitize_input(req.codebase, 50000)
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
        "Codebase:\n" + trim_codebase(req.codebase, 4000)
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
        "Codebase:\n" + trim_codebase(req.codebase, 3000) + "\n\n"
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
        "Codebase:\n" + trim_codebase(req.codebase, 4000)
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
    trimmed_codebase = trim_codebase(req.codebase, 3000)

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
        "a zero denominator.\n"
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
    fixes_text, fixes_stop = await ai_complete(
        [
            {"role": "system", "content": fixes_system_prompt},
            {"role": "user", "content": fixes_user_prompt},
        ],
        temperature=0.1,
        max_tokens=AUTO_FIXES_MAX_TOKENS,
    )
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
    patch_system_prompt = (
        "You are DataVireon in fully automatic resolution mode (step 2 of 2: patched file).\n"
        "The following fixes were already identified for this codebase — apply ALL of "
        "them together so the result is a single coherent, runnable program:\n"
        + json.dumps(fixes_data.get("fixes", [])) + "\n\n"
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
    patch_text, patch_stop = await ai_complete(
        [
            {"role": "system", "content": patch_system_prompt},
            {"role": "user", "content": patch_user_prompt},
        ],
        temperature=0.1,
        max_tokens=AUTO_PATCH_MAX_TOKENS,
    )
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
        f"Codebase:\n{sanitize_input(req.codebase, 6000)}"
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
