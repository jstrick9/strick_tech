"""Gap #012: chain step condition/transform eval was not sandboxed.

execute_chain evaluated user-influenced `step.condition`/`step.transform` with
bare {'__builtins__': {}}, which is *not* a sandbox — the attribute traversal
`().__class__.__base__.__subclasses__()` escapes it and reaches the
interpreter. Guard now rejects dunder/private access before eval.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.agent_engine import _safe_chain_eval
from backend.services.codeguard import reject_unsafe_attribute_usage


class TestChainEvalSandbox:
    def test_attribute_traversal_escape_is_rejected(self):
        payload = "().__class__.__base__.__subclasses__()"
        try:
            _safe_chain_eval(payload, {})
            raise AssertionError('escape payload was NOT rejected')
        except ValueError:
            pass

    def test_subclasses_traversal_rejected(self):
        try:
            _safe_chain_eval("().__class__.__mro__", {})
            raise AssertionError('__mro__ traversal was NOT rejected')
        except ValueError:
            pass

    def test_no_dunder_access_still_works(self):
        # Benign arithmetic/comparison unaffected.
        assert _safe_chain_eval("1 + 2 * 3", {}) == 7
        assert _safe_chain_eval("val > 1", {"val": 10}) is True
        assert _safe_chain_eval("'a' + 'b'", {}) == "ab"

    def test_context_lookup_still_works(self):
        assert _safe_chain_eval("name + name", {"name": "x"}) == "xx"

    def test_guard_rejects_dunder_directly(self):
        # codeguard.reject_unsafe_attribute_usage itself rejects dunder attr.
        try:
            reject_unsafe_attribute_usage("x.__class__", name="<t>")
            raise AssertionError('dunder attribute allowed')
        except ValueError:
            pass
