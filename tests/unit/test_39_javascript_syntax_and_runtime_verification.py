"""
Unit Tests — JavaScript Syntax & Runtime Verification Gate (`tests/unit/test_39_javascript_syntax_and_runtime_verification.py`)
Validates:
1. Strict ES syntax checks via node --check on all 15 controller scripts.
2. Zero TypeScript assertions (`as HTML...`, `:any`) and zero illegal left-hand optional chaining (`?.innerHTML=`).
3. 100% global window binding (`window.render<Name> = render<Name>`) for all 68 panes registered in MASTER_PANE_REGISTRY.
"""
from __future__ import annotations
import glob
import re
import shutil
import subprocess
from pathlib import Path
import pytest

from backend.config import get_data_dir
ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"
JS_DIR = FRONTEND_DIR / "js"


class TestJavaScriptSyntaxAndRuntimeVerification:
    """Suite formally guaranteeing 100% JavaScript syntax validity and global function binding."""

    @pytest.fixture(scope="class")
    def all_js_files(self):
        files = sorted(list(JS_DIR.glob("*.js")))
        assert len(files) >= 14, f"Expected at least 14 JS controllers in frontend/js/, found {len(files)}"
        return files

    def test_all_js_files_valid_es_syntax(self, all_js_files):
        """Run node --check across all JavaScript controllers to catch syntax and parse errors right during unit tests."""
        node_bin = shutil.which("node")
        if not node_bin:
            pytest.skip("Node.js binary not installed in test environment")

        failed_files = []
        for jf in all_js_files:
            res = subprocess.run([node_bin, "--check", str(jf)], capture_output=True, text=True)
            if res.returncode != 0:
                failed_files.append(f"{jf.name}: {res.stderr.strip()}")

        assert not failed_files, f"Syntax errors detected via node --check in JS files:\n" + "\n".join(failed_files)

    def test_no_typescript_or_illegal_optional_chaining_in_js_files(self, all_js_files):
        """Verify zero TypeScript artifacts (as HTML..., :any) or illegal left-hand optional chaining assignments."""
        ts_pattern = re.compile(r"\bas\s+HTML[a-zA-Z0-9_]+\b|\b\([a-zA-Z0-9_, ]+\)\s*:\s*any\b")
        lhs_opt_pattern = re.compile(r"\?\.[a-zA-Z0-9_]+\s*=(?!=)")

        violations = []
        for jf in all_js_files:
            text = jf.read_text(encoding="utf-8")
            ts_matches = ts_pattern.findall(text)
            if ts_matches:
                violations.append(f"{jf.name} has TypeScript assertions: {ts_matches[:3]}")
            lhs_matches = lhs_opt_pattern.findall(text)
            if lhs_matches:
                violations.append(f"{jf.name} has illegal left-hand optional chaining assignment: {lhs_matches[:3]}")

        assert not violations, f"Forbidden syntax artifacts found across JS controllers:\n" + "\n".join(violations)

    def test_all_68_master_pane_registry_functions_globally_bound(self, all_js_files):
        """Verify that every single function referenced in MASTER_PANE_REGISTRY is defined and attached across our scripts."""
        registry_js = (JS_DIR / "00-pane-registry.js").read_text(encoding="utf-8")
        match = re.search(r"window\.MASTER_PANE_REGISTRY = \{(.*?)\};", registry_js, re.DOTALL)
        assert match is not None, "window.MASTER_PANE_REGISTRY must exist in 00-pane-registry.js"

        reg_content = match.group(1)
        entries = re.findall(r"\x27([a-zA-Z0-9_-]+)\x27\s*:\s*\(\)\s*=>\s*(?:typeof\s+window\.([a-zA-Z0-9_]+)\s*===\s*\x27function\x27|\{\})", reg_content)
        assert len(entries) >= 68, f"Expected at least 68 pane entries in MASTER_PANE_REGISTRY, found {len(entries)}"

        all_text = "\n".join([jf.read_text(encoding="utf-8") for jf in all_js_files])
        all_text += "\n" + (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

        missing_binds = []
        for pane, fn_name in entries:
            if not fn_name:  # like chat -> () => {}
                continue
            # Check if defined as function fn_name( or assigned via window.fn_name =
            has_func = re.search(r"^(?:async\s+)?function\s+" + re.escape(fn_name) + r"\s*\(", all_text, re.MULTILINE)
            has_win = re.search(r"window\." + re.escape(fn_name) + r"\s*=", all_text)
            has_var = re.search(r"(?:var|let|const)\s+" + re.escape(fn_name) + r"\s*=\s*(?:async\s+)?(?:function|\()", all_text)

            if not (has_func or has_win or has_var):
                missing_binds.append((pane, fn_name))

        assert not missing_binds, f"MASTER_PANE_REGISTRY references functions missing across JS source files: {missing_binds}"
