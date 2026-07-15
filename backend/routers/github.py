"""
Agentic OS — GitHub Integration Router
Full bidirectional sync: OAuth connect, push, pull, branches, PRs,
repo create, deploy, and GitHub Pages — all from inside Agentic OS.
Matches or exceeds Lovable's GitHub integration.
"""
from __future__ import annotations
import asyncio, json, logging, os, subprocess, time, base64
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import httpx

router = APIRouter(prefix="/api/github", tags=["github"])
log    = logging.getLogger("agentic.github")
ROOT   = Path(__file__).resolve().parents[2]

GITHUB_API = "https://api.github.com"
GITHUB_AUTH = "https://github.com/login/oauth"


# ── Token helpers ──────────────────────────────────────────────────────────────
def _gh_token() -> str:
    """Get GitHub token from env (injected from vault or .env)."""
    return os.getenv("GITHUB_TOKEN", "")


def _gh_headers() -> dict:
    token = _gh_token()
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def _gh_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{GITHUB_API}{path}", headers=_gh_headers(), params=params or {})
        r.raise_for_status()
        return r.json()


async def _gh_post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(f"{GITHUB_API}{path}", headers=_gh_headers(), json=body)
        r.raise_for_status()
        return r.json()


async def _gh_put(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.put(f"{GITHUB_API}{path}", headers=_gh_headers(), json=body)
        r.raise_for_status()
        return r.json()


async def _gh_patch(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.patch(f"{GITHUB_API}{path}", headers=_gh_headers(), json=body)
        r.raise_for_status()
        return r.json()


# ── Status ─────────────────────────────────────────────────────────────────────
@router.get("/status")
async def github_status():
    """Full GitHub connection status."""
    token = _gh_token()
    if not token:
        return {
            "connected": False,
            "token_set": False,
            "setup": {
                "steps": [
                    "1. Go to https://github.com/settings/tokens",
                    "2. Click 'Generate new token (classic)'",
                    "3. Select scopes: repo, workflow, read:user, user:email",
                    "4. Copy the token",
                    "5. Add to .env: GITHUB_TOKEN=ghp_...",
                    "6. Or save via 🔐 Vault tab in Agentic OS",
                    "7. Restart Agentic OS",
                ],
                "token_url": "https://github.com/settings/tokens",
                "scopes_needed": ["repo", "workflow", "read:user", "user:email"],
            }
        }
    try:
        user = await _gh_get("/user")
        repos_data = await _gh_get("/user/repos", {"per_page": 10, "sort": "updated"})
        return {
            "connected": True,
            "token_set": True,
            "user": {
                "login":      user.get("login"),
                "name":       user.get("name"),
                "avatar_url": user.get("avatar_url"),
                "html_url":   user.get("html_url"),
                "public_repos": user.get("public_repos", 0),
                "plan":       user.get("plan", {}).get("name", "free"),
            },
            "recent_repos": [
                {"name": r["name"], "full_name": r["full_name"],
                 "private": r["private"], "url": r["html_url"],
                 "default_branch": r.get("default_branch", "main"),
                 "updated_at": r.get("updated_at","")[:10]}
                for r in repos_data[:8]
            ],
        }
    except httpx.HTTPStatusError as e:
        return {"connected": False, "token_set": True, "error": f"GitHub API error {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"connected": False, "token_set": True, "error": str(e)}


# ── Repositories ───────────────────────────────────────────────────────────────
@router.get("/repos")
async def list_repos(per_page: int = 30, sort: str = "updated"):
    """List user's GitHub repositories."""
    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        repos = await _gh_get("/user/repos", {"per_page": min(per_page, 100), "sort": sort})
        return {
            "ok": True,
            "repos": [
                {"name": r["name"], "full_name": r["full_name"],
                 "description": r.get("description", ""),
                 "private": r["private"], "url": r["html_url"],
                 "clone_url": r["clone_url"], "ssh_url": r["ssh_url"],
                 "default_branch": r.get("default_branch", "main"),
                 "topics": r.get("topics", []),
                 "updated_at": r.get("updated_at", "")[:10],
                 "language": r.get("language", "")}
                for r in repos
            ]
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/repos/create")
async def create_repo(req: Request):
    """Create a new GitHub repository for the current project."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    import re as _re
    name        = _re.sub(r"[^a-zA-Z0-9._-]", "-", (body.get("name") or "agentic-os-project").strip())[:100]
    name        = name.strip("-") or "agentic-os-project"  # remove leading/trailing hyphens
    description = body.get("description", "Built with Agentic OS")
    private     = bool(body.get("private", False))
    auto_init   = bool(body.get("auto_init", True))

    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set. Add it via 🔐 Vault or .env"}
    try:
        repo = await _gh_post("/user/repos", {
            "name": name, "description": description,
            "private": private, "auto_init": auto_init,
            "gitignore_template": "Python",
        })
        log.info("Created repo: %s", repo.get("full_name"))
        from ..services.memory_db import audit_log
        audit_log("github_repo_create", repo.get("full_name", ""))
        return {
            "ok":           True,
            "repo":         repo.get("full_name"),
            "url":          repo.get("html_url"),
            "clone_url":    repo.get("clone_url"),
            "default_branch": repo.get("default_branch", "main"),
        }
    except httpx.HTTPStatusError as e:
        data = e.response.json() if e.response.headers.get("content-type","").startswith("application/json") else {}
        return {"ok": False, "error": data.get("message", str(e))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Push to GitHub ─────────────────────────────────────────────────────────────
@router.post("/push")
async def push_to_github(req: Request):
    """
    Push preview/ directory to a GitHub repository.
    Uses GitHub Contents API (no local git required).
    """
    try:
        body      = await req.json()
    except Exception:
        body      = {}
    repo_name = body.get("repo", "").strip()          # e.g. "username/my-repo"
    branch    = body.get("branch", "main").strip()
    message   = body.get("message", "Agentic OS push").strip()
    directory = body.get("directory", "preview")      # which local dir to push

    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    if not repo_name:
        return {"ok": False, "error": "repo required (e.g. username/repo-name)"}

    source_dir = (ROOT / directory if directory != "preview" else ROOT / "preview").resolve()
    # Security: ensure source_dir is within ROOT
    if not str(source_dir).startswith(str(ROOT.resolve())):
        return {"ok": False, "error": "Invalid directory path (must be within project)"}
    if not source_dir.exists():
        return {"ok": False, "error": f"Directory '{directory}' not found"}

    files_pushed = 0
    errors       = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        # Collect all files
        _SKIP_DIRS = {".git", "__pycache__", "branches", "node_modules", ".next", "dist", "build"}
        _MAX_PUSH_SIZE = 5_000_000  # 5 MB per file limit for GitHub API
        file_paths = [
            f for f in source_dir.rglob("*")
            if f.is_file() and not any(skip in f.parts for skip in _SKIP_DIRS)
        ]
        total_files = len(file_paths)
        truncated = total_files > 100

        for file_path in file_paths[:100]:  # limit to 100 files
            rel_path = file_path.relative_to(source_dir).as_posix()
            try:
                content   = file_path.read_bytes()
                content_b64 = base64.b64encode(content).decode()

                # Check if file already exists (to get its SHA for update)
                sha = None
                check = await client.get(
                    f"{GITHUB_API}/repos/{repo_name}/contents/{rel_path}",
                    headers=_gh_headers(), params={"ref": branch}
                )
                if check.status_code == 200:
                    sha = check.json().get("sha")

                payload = {"message": f"{message} — {rel_path}", "content": content_b64, "branch": branch}
                if sha:
                    payload["sha"] = sha

                r = await client.put(
                    f"{GITHUB_API}/repos/{repo_name}/contents/{rel_path}",
                    headers=_gh_headers(), json=payload
                )
                if r.status_code in (200, 201):
                    files_pushed += 1
                else:
                    errors.append(f"{rel_path}: {r.status_code}")
            except Exception as e:
                errors.append(f"{rel_path}: {e}")

    from ..services.memory_db import audit_log, memory_add
    audit_log("github_push", f"{repo_name}/{branch}: {files_pushed} files")
    if files_pushed:
        memory_add("github", f"Pushed {files_pushed} files to github.com/{repo_name}/{branch}", "github,push,deploy")

    return {
        "ok":           files_pushed > 0,
        "repo":         repo_name,
        "branch":       branch,
        "files_pushed": files_pushed,
        "total_files":  total_files if 'total_files' in dir() else files_pushed,
        "truncated":    truncated if 'truncated' in dir() else False,
        "errors":       errors[:5],
        "url":          f"https://github.com/{repo_name}/tree/{branch}",
        "message":      message,
    }


# ── Pull from GitHub ───────────────────────────────────────────────────────────
@router.post("/pull")
async def pull_from_github(req: Request):
    """Pull files from a GitHub repository into preview/."""
    try:
        body      = await req.json()
    except Exception:
        body      = {}
    repo_name = body.get("repo", "").strip()
    branch    = body.get("branch", "main").strip()
    target    = body.get("target", "preview")

    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    if not repo_name:
        return {"ok": False, "error": "repo required"}

    target_dir = ROOT / "preview" if target == "preview" else ROOT / target
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get tree
        tree_data = await _gh_get(f"/repos/{repo_name}/git/trees/{branch}", {"recursive": "1"})
        blobs     = [item for item in tree_data.get("tree", []) if item["type"] == "blob"]

        files_pulled = 0
        async with httpx.AsyncClient(timeout=20.0) as client:
            for blob in blobs[:100]:
                path = blob["path"]
                # Only pull web-relevant files
                if any(path.endswith(ext) for ext in [".html",".css",".js",".jsx",".ts",".tsx",".json",".md",".svg",".txt"]):
                    blob_data = await client.get(blob["url"], headers=_gh_headers())
                    if blob_data.status_code == 200:
                        content_b64 = blob_data.json().get("content", "")
                        content     = base64.b64decode(content_b64.replace("\n",""))
                        f = (target_dir / path).resolve()
                        # Security: ensure resolved path stays inside target_dir
                        if not str(f).startswith(str(target_dir.resolve())):
                            log.warning("Blocked path traversal attempt: %s", path)
                            continue
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(content)
                        files_pulled += 1

        from ..services.memory_db import audit_log
        audit_log("github_pull", f"{repo_name}/{branch}: {files_pulled} files")
        return {"ok": True, "repo": repo_name, "branch": branch, "files_pulled": files_pulled}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Branches ───────────────────────────────────────────────────────────────────
@router.get("/repos/{owner}/{repo}/branches")
async def list_branches(owner: str, repo: str):
    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        branches = await _gh_get(f"/repos/{owner}/{repo}/branches")
        return {"ok": True, "branches": [b["name"] for b in branches]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/repos/{owner}/{repo}/branches")
async def create_branch(owner: str, repo: str, req: Request):
    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        body        = await req.json()
    except Exception:
        body        = {}
    branch_name = body.get("name", "").strip()
    from_branch = body.get("from", "main")
    if not branch_name:
        return {"ok": False, "error": "branch name required"}
    try:
        # Get SHA of source branch
        ref_data = await _gh_get(f"/repos/{owner}/{repo}/git/ref/heads/{from_branch}")
        sha      = ref_data["object"]["sha"]
        # Create new branch
        await _gh_post(f"/repos/{owner}/{repo}/git/refs", {
            "ref": f"refs/heads/{branch_name}", "sha": sha
        })
        return {"ok": True, "branch": branch_name, "from": from_branch,
                "url": f"https://github.com/{owner}/{repo}/tree/{branch_name}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Pull Requests ──────────────────────────────────────────────────────────────
@router.post("/repos/{owner}/{repo}/pulls")
async def create_pr(owner: str, repo: str, req: Request):
    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        body  = await req.json()
    except Exception:
        body  = {}
    title = body.get("title", "Agentic OS changes")
    head  = body.get("head", "")        # source branch
    base  = body.get("base", "main")    # target branch
    body_text = body.get("body", "Automated PR from Agentic OS")

    if not head:
        return {"ok": False, "error": "head branch required"}
    try:
        pr = await _gh_post(f"/repos/{owner}/{repo}/pulls", {
            "title": title, "head": head, "base": base, "body": body_text
        })
        from ..services.memory_db import audit_log
        audit_log("github_pr_create", f"{owner}/{repo} #{pr.get('number')}: {title}")
        return {
            "ok":     True,
            "number": pr.get("number"),
            "url":    pr.get("html_url"),
            "title":  title,
            "state":  pr.get("state"),
        }
    except httpx.HTTPStatusError as e:
        data = e.response.json() if "json" in e.response.headers.get("content-type","") else {}
        return {"ok": False, "error": data.get("message", str(e))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/repos/{owner}/{repo}/pulls")
async def list_prs(owner: str, repo: str, state: str = "open"):
    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        prs = await _gh_get(f"/repos/{owner}/{repo}/pulls", {"state": state, "per_page": 20})
        return {"ok": True, "pulls": [
            {"number": p["number"], "title": p["title"], "state": p["state"],
             "url": p["html_url"], "head": p["head"]["ref"], "base": p["base"]["ref"],
             "created_at": p.get("created_at","")[:10]}
            for p in prs
        ]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Commits ────────────────────────────────────────────────────────────────────
@router.get("/repos/{owner}/{repo}/commits")
async def list_commits(owner: str, repo: str, branch: str = "main", per_page: int = 20):
    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        commits = await _gh_get(f"/repos/{owner}/{repo}/commits",
                                 {"sha": branch, "per_page": min(per_page, 50)})
        return {"ok": True, "commits": [
            {"sha": c["sha"][:7], "message": c["commit"]["message"].split("\n")[0][:80],
             "author": c["commit"]["author"]["name"],
             "date": c["commit"]["author"]["date"][:10],
             "url": c.get("html_url","")}
            for c in commits
        ]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── GitHub Pages deploy ────────────────────────────────────────────────────────
@router.post("/pages/deploy")
async def deploy_github_pages(req: Request):
    """Deploy preview/ to GitHub Pages via gh-pages branch."""
    try:
        body      = await req.json()
    except Exception:
        body      = {}
    repo_name = body.get("repo", "").strip()
    message   = body.get("message", "Deploy to GitHub Pages via Agentic OS")

    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    if not repo_name:
        return {"ok": False, "error": "repo required (e.g. username/repo-name)"}

    # First push files to gh-pages branch
    push_result = await push_to_github(_make_internal_request({
        "repo": repo_name, "branch": "gh-pages", "message": message
    }))

    if not push_result.get("ok"):
        # Try creating gh-pages branch first
        owner, repo = repo_name.split("/", 1) if "/" in repo_name else ("", repo_name)
        try:
            main_ref = await _gh_get(f"/repos/{repo_name}/git/ref/heads/main")
            sha      = main_ref["object"]["sha"]
            await _gh_post(f"/repos/{repo_name}/git/refs",
                           {"ref": "refs/heads/gh-pages", "sha": sha})
        except Exception:
            pass
        push_result = await push_to_github(_make_internal_request({
            "repo": repo_name, "branch": "gh-pages", "message": message
        }))

    # Enable GitHub Pages if not already
    try:
        await _gh_post(f"/repos/{repo_name}/pages", {
            "source": {"branch": "gh-pages", "path": "/"}
        })
    except Exception:
        pass  # May already be enabled

    # Get pages URL
    try:
        pages = await _gh_get(f"/repos/{repo_name}/pages")
        pages_url = pages.get("html_url", f"https://{repo_name.split('/')[0]}.github.io/{repo_name.split('/')[1]}")
    except Exception:
        owner_name = repo_name.split("/")[0]
        repo_part  = repo_name.split("/")[1] if "/" in repo_name else repo_name
        pages_url  = f"https://{owner_name}.github.io/{repo_part}"

    from ..services.memory_db import audit_log, memory_add
    audit_log("github_pages_deploy", f"{repo_name} → {pages_url}")
    memory_add("deploy:github-pages", f"Deployed to {pages_url}", "deploy,github-pages")

    return {
        "ok":          push_result.get("ok", False),
        "url":         pages_url,
        "repo":        repo_name,
        "branch":      "gh-pages",
        "files":       push_result.get("files_pushed", 0),
        "tip":         "GitHub Pages may take 1-2 minutes to update after first deploy.",
    }


# ── Sync (bidirectional) ───────────────────────────────────────────────────────
@router.post("/sync")
async def sync_with_github(req: Request):
    """
    Bidirectional sync: push local preview/ to GitHub AND pull latest from GitHub.
    Like Lovable's auto-sync.
    """
    try:
        body      = await req.json()
    except Exception:
        body      = {}
    repo_name = body.get("repo", "").strip()
    branch    = body.get("branch", "main")
    direction = body.get("direction", "push")  # "push" | "pull" | "both"

    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    if not repo_name:
        return {"ok": False, "error": "repo required"}

    if direction not in ("push", "pull", "both"):
        return {"ok": False, "error": f"Invalid direction '{direction}'. Use: push, pull, or both"}

    results = {}
    if direction in ("push", "both"):
        results["push"] = await push_to_github(_make_internal_request({
            "repo": repo_name, "branch": branch, "message": f"Auto-sync from Agentic OS {time.strftime('%Y-%m-%d %H:%M')}"
        }))
    if direction in ("pull", "both"):
        results["pull"] = await pull_from_github(_make_internal_request({
            "repo": repo_name, "branch": branch
        }))

    ok_result = any(v.get("ok") for v in results.values()) if results else False
    return {"ok": ok_result, "direction": direction, "repo": repo_name, "branch": branch, **results}


# ── Repository info ────────────────────────────────────────────────────────────
@router.get("/repos/{owner}/{repo}")
async def get_repo(owner: str, repo: str):
    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        data = await _gh_get(f"/repos/{owner}/{repo}")
        return {
            "ok":             True,
            "name":           data["name"],
            "full_name":      data["full_name"],
            "description":    data.get("description"),
            "private":        data["private"],
            "url":            data["html_url"],
            "clone_url":      data["clone_url"],
            "default_branch": data.get("default_branch","main"),
            "stars":          data.get("stargazers_count",0),
            "forks":          data.get("forks_count",0),
            "language":       data.get("language"),
            "topics":         data.get("topics",[]),
            "has_pages":      data.get("has_pages",False),
            "pages_url":      f"https://{owner}.github.io/{repo}" if data.get("has_pages") else None,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Gists (quick share) ────────────────────────────────────────────────────────
@router.post("/gists")
async def create_gist(req: Request):
    """Share a file as a GitHub Gist."""
    try:
        body     = await req.json()
    except Exception:
        body     = {}
    filename = body.get("filename", "index.html")
    content  = body.get("content", "")
    desc     = body.get("description", "Shared from Agentic OS")
    public   = bool(body.get("public", True))

    if not _gh_token():
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    try:
        gist = await _gh_post("/gists", {
            "description": desc,
            "public":      public,
            "files":       {filename: {"content": content}}
        })
        return {"ok": True, "url": gist.get("html_url"), "id": gist.get("id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Helper ─────────────────────────────────────────────────────────────────────
def _fake_receive(data: dict):
    """Create a minimal ASGI receive callable for internal Request construction."""
    body_bytes = json.dumps(data).encode()
    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}
    return receive


def _make_internal_request(data: dict) -> Request:
    """Build a minimal FastAPI Request for internal delegation (sync/pages)."""
    return Request(
        scope={
            "type":    "http",
            "method":  "POST",
            "path":    "/internal",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        },
        receive=_fake_receive(data),
    )
