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
import httpx, os, json
import anthropic as _anthropic
from groq import Groq as _Groq

load_dotenv()

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
    steps_context = ""
    if req.previous_steps:
        steps_context = "\n\nPrevious steps:\n" + "\n".join(
            "Step " + str(s["step_number"]) + ": " + s["explanation"] + " — User: " + s["decision"]
            for s in req.previous_steps
        )
    override = ("\n\nUser instruction: " + req.override_prompt) if req.override_prompt else ""

    system_prompt = (
        "You are DataVireon, an expert code resolution assistant in semi-automatic mode.\n"
        "Provide ONE focused fix step. Return ONLY JSON:\n"
        "{\"step_title\":\"short title\","
        "\"explanation\":\"clear explanation of what and why\","
        "\"diff\":\"unified diff or full corrected code block\","
        "\"language\":\"python|sql|yaml|etc\","
        "\"is_final\":true_or_false}"
        "\nNo markdown. No text outside the JSON."
    )
    user_prompt = (
        "Role: " + req.role.replace("_", " ") + "\n"
        "Problem: " + req.problem + "\n"
        "Diagnostic: " + req.diagnostic + "\n"
        "Step number: " + str(req.step_number)
        + steps_context + override + "\n\n"
        "Codebase:\n" + trim_codebase(req.codebase, 3000) + "\n\n"
        "Provide step " + str(req.step_number) + " of the fix."
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
    skill_prompt = get_skill(req.role, req.diagnostic.get("domain", ""))

    system_prompt = (
        (skill_prompt + "\n\n") if skill_prompt else ""
    ) + (
        "You are DataVireon in fully automatic resolution mode.\n"
        "Analyze the codebase and apply ALL necessary fixes at once.\n"
        "Return ONLY JSON:\n"
        '{"fixes":['
        '{"title":"fix title",'
        '"explanation":"what was wrong and why this fixes it",'
        '"original":"original code snippet",'
        '"fixed":"corrected code snippet",'
        '"language":"python|sql|yaml|etc"}],'
        '"summary":"overall summary of all changes made",'
        '"patched_codebase":"the complete fixed codebase",'
        '"warnings":["any caveats or things to verify"]}'
        "\nNo markdown. No text outside JSON."
    )
    user_prompt = (
        "Role: " + req.role.replace("_", " ") + "\n"
        "Problem: " + req.problem + "\n"
        "Diagnostic: " + json.dumps(req.diagnostic) + "\n\n"
        "Codebase:\n" + trim_codebase(req.codebase, 3000) + "\n\n"
        "Apply all necessary fixes and return the complete patched codebase."
    )
    return StreamingResponse(
        await ai_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.1),
        media_type="text/plain",
    )

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
                if res.status_code == 200:
                    data = res.json()
                    schema_info += f"Table: {table}\n"
                    if data and isinstance(data, list) and len(data) > 0:
                        cols = list(data[0].keys())
                        schema_info += f"  Columns: {', '.join(cols)}\n"
                    else:
                        schema_info += f"  (empty table)\n"
                    schema_info += "\n"

            schema_info = f"Accessible tables: {', '.join(found_tables)}\n\n" + schema_info

    except httpx.TimeoutException:
        raise HTTPException(408, "Connection timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Schema fetch failed: {str(e)}")

    skill_prompt = get_skill(req.role, "schema_quality")
    system_prompt = (
        (skill_prompt + "\n\n") if skill_prompt else ""
    ) + (
        "You are DataVireon analyzing a live Supabase database schema.\n"
        "Identify schema quality issues, missing constraints, security gaps, and optimization opportunities.\n"
        "Return ONLY JSON:\n"
        "{\"domain\":\"schema_quality\","
        "\"severity\":\"critical|high|medium|low\","
        "\"confidence\":0.0_to_1.0,"
        "\"summary\":\"2-3 sentence summary\","
        "\"symptoms\":[\"issue1\",\"issue2\"],"
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
