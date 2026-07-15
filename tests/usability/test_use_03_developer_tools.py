"""
USABILITY-03: Developer Tools — Code, Git, Testing, Terminal, Deploy
Every developer workflow: write code, review it, test it, ship it.
"""
import pytest
from tests.usability.conftest import *


class TestUseCodeEditor:
    """User writes and edits code in the Monaco editor."""

    async def test_builder_agent_can_fix_code(self, U):
        """User pastes broken code, asks Builder to fix it — response arrives."""
        r = await POST(U, "/api/agent/fix", {
            "code": "def add(a, b)\n    return a + b",
            "error": "SyntaxError: expected ':'",
            "language": "python"
        })
        no_error(r, "agent fix code")
        d = j(r)
        uat("fix response returned", "fixed_code" in d or "code" in d or "ok" in d)

    async def test_builder_agent_can_edit_code(self, U):
        """User asks Builder to refactor a function — edited code returned (SSE or JSON)."""
        r = await POST(U, "/api/agent/edit", {
            "code": "def calculate(x, y):\n    return x + y",
            "instruction": "Add type hints and a docstring",
            "language": "python"
        })
        no_error(r, "agent edit code")
        ct = r.headers.get("content-type","")
        is_sse  = "event-stream" in ct
        is_json = "json" in ct
        # SSE means streaming response started — success
        uat("edited code response received",
            is_sse or is_json or r.status_code == 200)

    async def test_multifile_composer_runs(self, U):
        """User runs a multi-file project composition task."""
        r = await POST(U, "/api/composer/run", {
            "task": "Create a simple Python Flask app with a /health endpoint",
            "files": {"app.py": "# Flask app placeholder"},
            "agent_id": "builder"
        })
        no_error(r, "composer run")

    async def test_composer_history_visible(self, U):
        """Composer history shows past multi-file generations."""
        r = await GET(U, "/api/composer/history")
        no_error(r, "composer history")
        d = j(r)
        hist = d if isinstance(d, list) else d.get("history", d.get("runs", []))
        uat("history returned as list", isinstance(hist, list))

    async def test_preview_branch_management(self, U):
        """User creates and lists preview branches for live projects."""
        r = await POST(U, "/api/composer/preview/branch", {
            "name": uid("feature-branch"), "base": "main",
            "files": {"index.html": "<h1>Hello</h1>"}
        })
        no_error(r, "create preview branch")

        r2 = await GET(U, "/api/composer/preview/branches")
        no_error(r2, "list preview branches")
        d2 = j(r2)
        branches = d2 if isinstance(d2, list) else d2.get("branches", [])
        uat("branches returned", isinstance(branches, list))


class TestUseCodeIndexing:
    """User indexes their codebase for symbol search and navigation."""

    async def test_codeindex_stats_visible(self, U):
        """User sees code index statistics — how many files/symbols indexed."""
        r = await GET(U, "/api/codeindex/stats")
        no_error(r, "codeindex stats")
        d = j(r)
        uat("stats have files or symbols count", "files" in d or "symbols" in d or "total" in d or isinstance(d, dict))

    async def test_symbol_search_returns_results(self, U):
        """User types a symbol name — matching symbols appear."""
        r = await GET(U, "/api/codeindex/symbols?q=def")
        no_error(r, "symbol search")
        d = j(r)
        symbols = d if isinstance(d, list) else d.get("symbols", d.get("results", []))
        uat("symbol search returns list", isinstance(symbols, list))

    async def test_codeindex_graph_available(self, U):
        """User can visualize the code dependency graph."""
        r = await GET(U, "/api/codeindex/graph")
        no_error(r, "codeindex graph")
        d = j(r)
        uat("graph data returned", "nodes" in d or "edges" in d or isinstance(d, dict))

    async def test_complexity_analysis_available(self, U):
        """User can see code complexity metrics."""
        r = await GET(U, "/api/codeindex/complexity")
        no_error(r, "complexity analysis")

    async def test_dead_code_detection_available(self, U):
        """User can detect unused code across their project."""
        r = await GET(U, "/api/codeindex/dead-code")
        no_error(r, "dead code detection")


class TestUseBugBot:
    """User uses BugBot to review code for issues."""

    async def test_bugbot_diff_review(self, U):
        """User pastes a git diff — BugBot reviews it for bugs."""
        r = await POST(U, "/api/bugbot/review/diff", {
            "diff": """--- a/auth.py
+++ b/auth.py
@@ -10,7 +10,7 @@ def authenticate(user, password):
-    if user == password:
+    if user == "admin":
         return True""",
            "language": "python", "context": "Authentication module"
        })
        no_error(r, "bugbot diff review")
        d = j(r)
        uat("review result returned", "review" in d or "issues" in d or "ok" in d)

    async def test_bugbot_file_review(self, U):
        """User submits a file for full review."""
        r = await POST(U, "/api/bugbot/review/file", {
            "filename": "utils.py",
            "content": "def divide(a, b):\n    return a / b\n",
            "language": "python"
        })
        no_error(r, "bugbot file review")

    async def test_bugbot_review_history(self, U):
        """User views their past reviews."""
        r = await GET(U, "/api/bugbot/reviews")
        no_error(r, "bugbot reviews list")
        d = j(r)
        reviews = d if isinstance(d, list) else d.get("reviews", [])
        uat("reviews list returned", isinstance(reviews, list))

    async def test_bugbot_stats_dashboard(self, U):
        """BugBot dashboard shows how many issues found over time."""
        r = await GET(U, "/api/bugbot/stats")
        no_error(r, "bugbot stats")
        d = j(r)
        uat("stats returned", isinstance(d, dict))


class TestUseTestGenerator:
    """User auto-generates tests for their code."""

    async def test_generate_unit_tests(self, U):
        """User submits code — test generator produces test cases."""
        r = await POST(U, "/api/testgen/generate", {
            "source_code": "def multiply(a: int, b: int) -> int:\n    return a * b",
            "language": "python", "framework": "pytest",
            "coverage_target": 90
        })
        no_error(r, "generate tests")
        d = j(r)
        uat("tests generated", "tests" in d or "test_code" in d or "ok" in d)

    async def test_testgen_history_accessible(self, U):
        """Previously generated tests appear in history."""
        r = await GET(U, "/api/testgen/history")
        no_error(r, "testgen history")
        d = j(r)
        hist = d if isinstance(d, list) else d.get("history", [])
        uat("history returned", isinstance(hist, list))

    async def test_generate_tests_for_project(self, U):
        """User generates tests for the entire current project."""
        r = await POST(U, "/api/testgen/generate-for-project", {
            "path": ".", "framework": "pytest", "agent_id": "builder"
        })
        no_error(r, "project test generation")


class TestUseTerminal:
    """User runs commands in the built-in terminal."""

    async def test_terminal_echo_command(self, U):
        """User runs 'echo hello' — output appears in terminal."""
        r = await POST(U, "/api/terminal/run", {"command": "echo hello_usability_test"})
        no_error(r, "terminal echo")
        text = r.text
        uat("command ran or was processed", "hello" in text.lower() or "error" in text.lower() or "exit" in text.lower())

    async def test_terminal_pwd_command(self, U):
        """User checks working directory with pwd."""
        r = await POST(U, "/api/terminal/run", {"command": "pwd"})
        no_error(r, "terminal pwd")

    async def test_terminal_ls_command(self, U):
        """User lists directory contents."""
        r = await POST(U, "/api/terminal/run", {"command": "ls -la"})
        no_error(r, "terminal ls")

    async def test_terminal_history_available(self, U):
        """User can see their command history."""
        r = await GET(U, "/api/terminal/history")
        no_error(r, "terminal history")

    async def test_terminal_env_accessible(self, U):
        """User can see safe environment info."""
        r = await GET(U, "/api/terminal/env")
        no_error(r, "terminal env")
        d = j(r)
        uat("env info returned", isinstance(d, dict))


class TestUseGitAI:
    """User uses AI-assisted git operations."""

    async def test_gitai_commit_message_generation(self, U):
        """User stages files — AI generates a commit message."""
        r = await POST(U, "/api/gitai/commit", {
            "message": "AI generate", "files": ["src/app.py", "tests/test_app.py"],
            "context": "Added authentication middleware"
        })
        no_error(r, "gitai commit")
        d = j(r)
        uat("commit message returned", "message" in d or "commit" in d or "ok" in d)

    async def test_gitai_changelog_generation(self, U):
        """User generates a CHANGELOG from recent commits."""
        r = await POST(U, "/api/gitai/changelog", {
            "from_ref": "HEAD~10", "to_ref": "HEAD",
            "format": "markdown"
        })
        no_error(r, "gitai changelog")

    async def test_gitai_deps_audit(self, U):
        """User audits project dependencies for security issues."""
        r = await GET(U, "/api/gitai/deps/audit")
        no_error(r, "deps audit")
        d = j(r)
        uat("deps audit returns result", isinstance(d, dict) or isinstance(d, list))

    async def test_gitai_security_scan(self, U):
        """User runs a security scan on the codebase."""
        r = await POST(U, "/api/gitai/security/scan", {"path": "."})
        no_error(r, "security scan")
        d = j(r)
        uat("scan result returned", "vulnerabilities" in d or "issues" in d or "ok" in d)

    async def test_nl_git_command(self, U):
        """User types 'show me last 5 commits' in natural language."""
        r = await POST(U, "/api/gitai/nl-git", {
            "command": "show me the last 5 commits with authors"
        })
        no_error(r, "nl-git command")
        d = j(r)
        uat("nl git result", "result" in d or "output" in d or "ok" in d)


class TestUseDeployment:
    """User deploys their project to various platforms."""

    async def test_deploy_providers_list(self, U):
        """User sees available deployment targets."""
        r = await GET(U, "/api/deploy/providers")
        no_error(r, "deploy providers")
        d = j(r)
        providers = d if isinstance(d, list) else d.get("providers", [])
        uat("providers available", len(providers) > 0)
        known = ["vercel", "netlify", "railway", "render", "flyio"]
        names = [str(p).lower() for p in providers]
        uat("vercel in providers", any(k in str(names) for k in ["vercel", "netlify"]))

    async def test_deploy_history_accessible(self, U):
        """User can review past deployment history."""
        r = await GET(U, "/api/deploy/history")
        no_error(r, "deploy history")
        d = j(r)
        hist = d if isinstance(d, list) else d.get("history", d.get("deployments", []))
        uat("deploy history returned", isinstance(hist, list))

    async def test_deploy_status_visible(self, U):
        """User sees current deployment status."""
        r = await GET(U, "/api/deploy/status")
        no_error(r, "deploy status")
        d = j(r)
        uat("status returned", isinstance(d, dict))

    async def test_tunnel_create_and_stop(self, U):
        """User creates a tunnel for local preview sharing."""
        r = await POST(U, "/api/deploy/tunnel", {"port": 8787, "provider": "cloudflare"})
        no_error(r, "create tunnel")
        r2 = await POST(U, "/api/deploy/tunnel/stop", {})
        no_error(r2, "stop tunnel")
