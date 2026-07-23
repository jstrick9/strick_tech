"""
SEC-08: Remote Code Execution & Filesystem Security
Comprehensive RCE and path traversal tests across ALL components
that could potentially execute code or access the filesystem.
"""
import pytest
from tests.security.conftest import *

# ─────────────────────────────────────────────────────────────────────────────
# TERMINAL ROUTER — Highest Risk
# ─────────────────────────────────────────────────────────────────────────────

RCE_PAYLOADS = [
    "whoami",
    "id",
    "cat /etc/passwd",
    "ls /",
    "env",
    "printenv",
    "pwd",
    "hostname",
    "uname -a",
    "; whoami",
    "| id",
    "& whoami",
    "&& cat /etc/passwd",
    "|| id",
    "$(whoami)",
    "`id`",
    "${IFS}cat${IFS}/etc/passwd",
    "1; whoami #",
    "1 | whoami",
    "1 && id",
    "\nwhoami",
    "\r\nid",
    "test\x00whoami",
]

PATH_TRAVERSAL = [
    "../../../etc/passwd",
    "../../etc/shadow",
    "..%2F..%2F..%2Fetc%2Fpasswd",
    "..%252F..%252Fetc%252Fpasswd",
    "....//....//etc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..\\..\\..\\etc\\passwd",
    "/etc/passwd",
    "/etc/shadow",
    "/proc/self/environ",
    "/proc/self/cmdline",
    "/root/.ssh/id_rsa",
    "/home/user/.env",
    "C:\\Windows\\System32\\drivers\\etc\\hosts",
]


class TestSecTerminalRCE:
    """Terminal endpoint — highest risk, must sandbox all command execution."""

    async def test_terminal_run_rce_payloads(self, C):
        """Terminal run must sandbox all command payloads.
        The terminal has an allowlist; error messages may echo the command
        but must NOT return actual RCE output (uid=0, /etc/passwd contents, etc.)."""
        for payload in RCE_PAYLOADS[:12]:
            r = await POST(C, "/api/terminal/run", {"command": payload})
            sec_ok(r, f"Terminal RCE: {payload[:30]}")
            body = r.text
            # Check for actual command execution output — NOT error messages
            rce_evidence = [
                "uid=0(root)", "uid=1000(user)", "root:x:0:0:",  # /etc/passwd line
                "bin/bash: root", "HOME=/root\n", "SHELL=/bin/bash\n",
                "Linux version", "x86_64 GNU/Linux",
            ]
            for marker in rce_evidence:
                assert marker not in body, \
                    f"Terminal RCE evidence '{marker}' found for payload: {payload[:30]}"

    async def test_terminal_run_path_injection(self, C):
        """Path injection in terminal command must not return file contents.
        Error messages may echo the path but must not return actual file data."""
        for p in PATH_TRAVERSAL[:8]:
            r = await POST(C, "/api/terminal/run", {"command": f"cat {p}"})
            sec_ok(r, f"Terminal path injection: {p[:30]}")
            body = r.text
            # These are actual /etc/passwd file content markers — NOT path strings
            actual_file_contents = [
                "root:x:0:0:root:", "daemon:x:1:1:",
                "nobody:x:65534:", "shadow:x:42:",
            ]
            for marker in actual_file_contents:
                assert marker not in body, \
                    f"Terminal path traversal succeeded — actual file content found: '{marker}'"

    async def test_terminal_env_var_exfil(self, C):
        """Terminal env variable commands must never leak API keys.
        The terminal allows 'echo' but blocks 'printenv'/'env'.
        Critical invariant: OPENROUTER_API_KEY must never appear in output."""
        env_attacks = ["printenv", "env", "cat /proc/self/environ", "echo $HOME $USER $PATH"]
        for cmd in env_attacks:
            r = await POST(C, "/api/terminal/run", {"command": cmd})
            sec_ok(r, f"Terminal env exfil: {cmd}")
            body = r.text
            # These are the real secrets that must NEVER appear
            critical_secrets = [
                "OPENROUTER_API_KEY=sk-",
                "sk-or-v1-",           # OpenRouter key format
                "OPENAI_API_KEY=sk-",
                "ANTHROPIC_API_KEY=",
            ]
            for danger in critical_secrets:
                assert danger not in body, \
                    f"CRITICAL: API key leaked via terminal '{cmd}': found '{danger}'"

    async def test_terminal_kill_injection(self, C):
        """Injection in terminal kill endpoint run_id."""
        for p in ["' OR 1=1 --", "$(whoami)", "../../etc"]:
            r = await POST(C, f"/api/terminal/kill/{p}", {})
            sec_ok(r, f"Terminal kill injection: {p[:20]}")


class TestSecProfilerRCE:
    """Profiler — must not allow arbitrary code profiling."""

    async def test_profiler_run_injection(self, C):
        """Profiler run with injected code path must not execute."""
        for p in ["import os; os.system('id')", "/etc/passwd", "$(whoami)", "__import__('os').system('id')"]:
            r = await POST(C, "/api/profiler/profile/run", {
                "target": p,
                "duration": 1
            })
            sec_ok(r, f"Profiler run injection: {p[:30]}")
            no_rce(r, f"Profiler injection: {p[:20]}")

    async def test_profiler_flamegraph_path_traversal(self, C):
        """Flamegraph endpoint with path traversal."""
        for p in PATH_TRAVERSAL[:6]:
            r = await GET(C, f"/api/profiler/flamegraph?path={p}")
            sec_ok(r, f"Profiler flamegraph path: {p[:30]}")
            no_path_escape(r, f"Profiler flamegraph: {p[:20]}")


class TestSecE2ERCE:
    """E2E test runner — must not execute arbitrary Playwright scripts."""

    async def test_e2e_run_injection(self, C):
        """E2E run with injected test code must not execute arbitrary commands."""
        malicious_scripts = [
            "const {exec} = require('child_process'); exec('whoami')",
            "process.env.OPENROUTER_API_KEY",
            "require('fs').readFileSync('/etc/passwd')",
            "import subprocess; subprocess.run(['id'])",
        ]
        for script in malicious_scripts:
            r = await POST(C, "/api/e2e/run", {
                "url": "http://localhost:8787",
                "test_code": script,
                "timeout": 5
            })
            sec_ok(r, f"E2E run injection: {script[:30]}")
            no_rce(r, f"E2E injection: {script[:20]}")

    async def test_e2e_run_url_ssrf(self, C):
        """E2E run targeting internal URLs must not expose internal data."""
        ssrf_urls = [
            "http://169.254.169.254/",
            "file:///etc/passwd",
            "http://127.0.0.1:6379",
        ]
        for url in ssrf_urls:
            r = await POST(C, "/api/e2e/run", {
                "url": url,
                "timeout": 3
            })
            sec_ok(r, f"E2E SSRF: {url}")


class TestSecTestgenRCE:
    """Test generator must not execute generated test code on the server."""

    async def test_testgen_generate_injection(self, C):
        """Test generation with injected code must not execute."""
        for p in RCE_PAYLOADS[:6]:
            r = await POST(C, "/api/testgen/generate", {
                "source_code": f"import os\nos.system('{p}')",
                "language": "python",
                "framework": "pytest"
            })
            sec_ok(r, f"Testgen injection: {p[:20]}")
            no_rce(r, f"Testgen: {p[:15]}")

    async def test_testgen_run_injection(self, C):
        """Running generated tests must be sandboxed."""
        r = await POST(C, "/api/testgen/run", {
            "test_code": "import os; os.system('id')",
            "language": "python"
        })
        sec_ok(r, "Testgen run injection")
        no_rce(r, "Testgen run")


class TestSecGitAIRCE:
    """GitAI operations — must not allow arbitrary git commands or file reads."""

    async def test_gitai_commit_message_injection(self, C):
        """Injection in git commit message must not execute shell commands."""
        for p in ["$(whoami)", "; id ;", "' && cat /etc/passwd && '", "`id`"]:
            r = await POST(C, "/api/gitai/commit", {
                "message": f"feat: update {p}",
                "files": []
            })
            sec_ok(r, f"GitAI commit injection: {p[:20]}")
            no_rce(r, f"GitAI commit: {p[:15]}")

    async def test_gitai_nl_git_injection(self, C):
        """Natural language git commands with injection."""
        for p in ["list all files in /etc", "show me /etc/passwd", "run id command"]:
            r = await POST(C, "/api/gitai/nl-git", {"command": p})
            sec_ok(r, f"GitAI NL injection: {p[:30]}")
            no_rce(r, f"GitAI NL: {p[:20]}")

    async def test_gitai_security_scan_path_injection(self, C):
        """Security scan with path traversal must not return /etc/passwd contents.
        The endpoint may scan within the project only; traversal outside must fail."""
        for p in PATH_TRAVERSAL[:6]:
            r = await POST(C, "/api/gitai/security/scan", {"path": p})
            sec_ok(r, f"GitAI scan path: {p[:30]}")
            body = r.text
            # Actual /etc/passwd file content markers
            actual_passwd_content = [
                "root:x:0:0:root:", "daemon:x:1:1:",
                "nobody:x:65534:", "shadow:x:42:",
            ]
            for marker in actual_passwd_content:
                assert marker not in body, \
                    f"GitAI scan path traversal succeeded — /etc/passwd content: '{marker}'"

    async def test_gitai_security_scan_file_injection(self, C):
        """Per-file security scan path traversal."""
        for p in PATH_TRAVERSAL[:6]:
            r = await POST(C, "/api/gitai/security/scan/file", {
                "file_path": p,
                "content": "test content"
            })
            sec_ok(r, f"GitAI file scan path: {p[:30]}")
            no_path_escape(r, f"GitAI file scan: {p[:20]}")

    async def test_gitai_deps_audit_path_injection(self, C):
        """Dependencies audit path injection."""
        for p in PATH_TRAVERSAL[:4]:
            r = await GET(C, f"/api/gitai/deps/audit?path={p}")
            sec_ok(r, f"GitAI deps path: {p[:20]}")
            no_path_escape(r, f"GitAI deps: {p[:15]}")


class TestSecBuilderRCE:
    """Builder/Monaco code editor — must not execute server-side code."""

    async def test_builder_agent_fix_rce(self, C):
        """Agent fix endpoint sends code to LLM (not executed server-side).
        Must not return actual command execution output."""
        for p in RCE_PAYLOADS[:8]:
            r = await POST(C, "/api/agent/fix", {
                "code": f"import os; os.system('{p}')",
                "error": "test error",
                "language": "python"
            })
            sec_ok(r, f"Builder fix RCE: {p[:20]}")
            body = r.text
            # Actual OS command output — not LLM-generated suggestions
            rce_evidence = [
                "uid=0(root)", "uid=1000(user)", "root:x:0:0:",
                "Linux version", "x86_64 GNU/Linux",
            ]
            for marker in rce_evidence:
                assert marker not in body, \
                    f"Builder fix RCE evidence '{marker}' for payload: {p[:20]}"

    async def test_builder_agent_edit_rce(self, C):
        """Agent edit with code injection."""
        for p in ["$(id)", "`whoami`", "__import__('os').system('id')"]:
            r = await POST(C, "/api/agent/edit", {
                "code": p,
                "instruction": "make it work",
                "language": "python"
            })
            sec_ok(r, f"Builder edit RCE: {p[:20]}")
            no_rce(r, f"Builder edit: {p[:15]}")


class TestSecCodeIndexRCE:
    """Code index — must not expose filesystem structure."""

    async def test_codeindex_index_path_traversal(self, C):
        """Code indexing with path traversal."""
        for p in PATH_TRAVERSAL[:6]:
            r = await POST(C, "/api/codeindex/index", {"path": p})
            sec_ok(r, f"Codeindex path: {p[:30]}")
            no_path_escape(r, f"Codeindex: {p[:20]}")

    async def test_codeindex_file_path_traversal(self, C):
        """Codeindex file endpoint queries SQLite DB (not actual filesystem).
        Path traversal attempts are echoed in filepath field but never read from disk.
        Critical check: must not return actual /etc/passwd file content."""
        for p in PATH_TRAVERSAL[:6]:
            encoded = p.replace("/", "%2F")
            r = await GET(C, f"/api/codeindex/file/{encoded}")
            sec_ok(r, f"Codeindex file path: {p[:30]}")
            body = r.text
            # Actual file content from /etc/passwd (not the path string in filepath field)
            actual_passwd_content = [
                "root:x:0:0:root:", "daemon:x:1:1:",
                "nobody:x:65534:", "shadow:x:42:",
            ]
            for marker in actual_passwd_content:
                assert marker not in body, \
                    f"Codeindex returned actual file content: '{marker}'"

    async def test_codeindex_dead_code_injection(self, C):
        """Dead code analysis path injection."""
        for p in PATH_TRAVERSAL[:4]:
            r = await GET(C, f"/api/codeindex/dead-code?path={p}")
            sec_ok(r, f"Codeindex dead-code path: {p[:20]}")
            no_path_escape(r, f"Codeindex dead-code: {p[:15]}")


class TestSecObsidianFilesystem:
    """Obsidian integration — must not read arbitrary filesystem paths."""

    async def test_obsidian_note_path_traversal(self, C):
        """Obsidian note creation must block path traversal outside vault.
        Obsidian router has built-in path traversal protection.
        URL-encoded traversal attempts are treated as literal filenames (safe)."""
        safe_traversals = [  # These are URL-encoded — treated as literals
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "%2e%2e%2fetc%2fpasswd",
        ]
        dangerous_traversals = [  # Real path traversal attempts
            "../../etc/passwd",
            "../../../etc/shadow",
        ]
        # URL-encoded variants should be stored as literal filenames (safe)
        for p in safe_traversals:
            r = await POST(C, "/api/obsidian/note", {"title": p, "content": "test", "path": p})
            sec_ok(r, f"Obsidian URL-encoded path: {p[:30]}")

        # Real path traversal must be blocked
        for p in dangerous_traversals:
            r = await POST(C, "/api/obsidian/note", {"title": p, "content": "test", "path": p})
            sec_ok(r, f"Obsidian path traversal: {p[:30]}")
            body = r.text
            # Must not succeed in reading actual /etc/passwd content
            actual_passwd = ["root:x:0:0:root:", "daemon:x:1:1:"]
            for marker in actual_passwd:
                assert marker not in body, \
                    f"Obsidian path traversal succeeded — file content: '{marker}'"

    async def test_obsidian_export_path_traversal(self, C):
        """Obsidian export with path traversal destination."""
        for p in PATH_TRAVERSAL[:6]:
            r = await POST(C, "/api/obsidian/export", {"destination": p, "format": "md"})
            sec_ok(r, f"Obsidian export path: {p[:30]}")
            no_path_escape(r, f"Obsidian export: {p[:20]}")

    async def test_obsidian_daily_note_path_injection(self, C):
        """Daily note with injection in date field."""
        for p in ["'; DROP TABLE notes; --", "$(whoami)", "../../etc/passwd", "2024-01-01/../../../"]:
            r = await POST(C, "/api/obsidian/daily_note", {"date": p, "content": "test"})
            sec_ok(r, f"Obsidian daily note: {p[:30]}")


class TestSecDeployRCE:
    """Deploy endpoints — must not allow arbitrary command execution."""

    async def test_deploy_tunnel_injection(self, C):
        """Deploy tunnel with injected port/command."""
        for p in ["8787; whoami", "$(id)", "' OR 1=1 --", "`id`"]:
            r = await POST(C, "/api/deploy/tunnel", {"port": p, "provider": "cloudflare"})
            sec_ok(r, f"Deploy tunnel injection: {p[:20]}")
            no_rce(r, f"Deploy tunnel: {p[:15]}")

    async def test_tauri_build_injection(self, C):
        """Tauri build with injected parameters."""
        for p in ["$(whoami)", "; id ;", "../../etc", "&& cat /etc/passwd"]:
            r = await POST(C, "/api/tauri/build", {"target": p, "release": False})
            sec_ok(r, f"Tauri build injection: {p[:20]}")
            no_rce(r, f"Tauri build: {p[:15]}")

    async def test_deploy_github_pages_injection(self, C):
        """GitHub Pages deploy with injected repo name."""
        for p in ["'; whoami #", "$(id)", "../../etc", "attacker/evil-repo"]:
            r = await POST(C, "/api/deploy/github-pages", {
                "repo": p, "branch": "gh-pages"
            })
            sec_ok(r, f"Deploy GH Pages injection: {p[:20]}")


class TestSecSystemGitRCE:
    """System git commands — must be sandboxed."""

    async def test_system_git_commit_injection(self, C):
        """System git commit with injected message."""
        for p in ["$(whoami)", "; id ;", "' && cat /etc/passwd"]:
            r = await POST(C, "/api/system/git/commit", {
                "message": p,
                "files": [],
                "push": False
            })
            sec_ok(r, f"System git commit injection: {p[:20]}")
            # Note: /api/system/git/commit passes the message straight to
            # GitPython's `repo.index.commit(message)`, which never invokes a
            # shell — the payload is stored as a literal commit message, not
            # executed. The endpoint's JSON response legitimately echoes that
            # literal string back (e.g. {"message": "' && cat /etc/passwd"}),
            # so a bare substring check for "/etc/passwd" false-positives on
            # the safely-reflected input. Instead assert the shell command
            # was never actually run by checking for real command output
            # signatures (e.g. the structural start of /etc/passwd's actual
            # contents, or a bare `uid=` from a real `id` invocation).
            body = r.text.lower()
            rce_evidence = ["root:x:0:0:", "uid=0(", "uid=1000("]
            for marker in rce_evidence:
                assert marker not in body, \
                    f"SEC RCE: System git commit: {p[:15]} — Found real command output '{marker}': {r.text[:300]}"

    async def test_workspace_save_path_traversal(self, C):
        """Workspace save with path traversal in filename."""
        workspaces = (await GET(C, "/api/workspaces")).json()
        ws_list = workspaces if isinstance(workspaces, list) else workspaces.get("workspaces", [])
        if not ws_list:
            pytest.skip("No workspaces to test")
        wsid = ws_list[0]["id"]
        for p in PATH_TRAVERSAL[:4]:
            r = await POST(C, f"/api/workspaces/{wsid}/save", {
                "filename": p,
                "content": "test"
            })
            sec_ok(r, f"Workspace save path: {p[:20]}")
            no_path_escape(r, f"Workspace save: {p[:15]}")
