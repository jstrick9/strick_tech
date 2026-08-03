"""
Unit Tests — Platform consolidation, Phase A
(`tests/unit/test_49_platform_consolidation.py`)

Guards two related cleanups:

1. Seven routers shipped API surface that NO user interface ever called
   (robotics, BCI, satellite, digital-twin, compiler, P2P sharding, telephony).
   They were stubs with no hardware/protocol integration — no ROS, MQTT, serial,
   WebRTC or Twilio client anywhere — so they could not do the thing their
   OpenAPI descriptions claimed. Removed rather than left as dead weight.

2. The Supervisor "Multi-Node Edge Radar" was the inverse problem: a real,
   working /api/cluster router wired to a completely fake UI. Its buttons
   invented results with setTimeout (claiming scanned subnets, discovered
   nodes and rebalanced load percentages) and its node list was three
   hardcoded cards naming invented hardware. It now uses the real endpoints.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PY = (ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')
SUPERVISOR_JS = (ROOT / 'frontend' / 'js' / '48-supervisor.js').read_text(encoding='utf-8')

# Assertions about removed fiction must inspect executable code only — the
# comments deliberately quote the old fabricated strings to explain the fix.
SUPERVISOR_CODE = '\n'.join(
    ln for ln in SUPERVISOR_JS.splitlines()
    if not ln.lstrip().startswith(('//', '*', '/*'))
)

REMOVED = ['robotics', 'bci', 'satellite', 'digital_twin', 'compiler', 'p2p_sharding', 'telephony']


class TestUnreachableRoutersRemoved:
    """UI-less stub routers must be gone, with no dangling references."""

    def test_router_modules_deleted(self):
        for mod in REMOVED:
            assert not (ROOT / 'backend' / 'routers' / f'{mod}.py').exists(), f'{mod}.py should be removed'

    def test_no_imports_remain_in_app(self):
        for mod in REMOVED:
            assert f'from .routers.{mod} import' not in APP_PY

    def test_no_include_router_calls_remain(self):
        for mod in REMOVED:
            assert f'app.include_router({mod}_router)' not in APP_PY

    def test_no_openapi_tags_remain(self):
        for tag in ('robotics', 'bci', 'satellite', 'digital-twin', 'compiler', 'p2p-sharding', 'telephony'):
            assert f"'name': '{tag}'" not in APP_PY

    def test_app_still_imports(self):
        # Guards against a half-finished removal leaving app.py unimportable.
        import backend.app  # noqa: F401


class TestClusterUiUsesRealApi:
    """The Edge Radar must reflect real registered nodes, not invented ones."""

    def test_fabricated_hardware_cards_are_gone(self):
        for fiction in (
            'MacBook Pro M3 Max',
            'MacBook Air M2',
            'RTX 4090',
            'ACTIVE · 1.1ms',
            'STANDBY · 4.8ms',
        ):
            assert fiction not in SUPERVISOR_CODE, f'hardcoded fiction still present: {fiction}'

    def test_node_list_is_rendered_from_the_api(self):
        assert "id=\"cluster-node-list\"" in SUPERVISOR_JS
        assert "fetch('/api/cluster/nodes')" in SUPERVISOR_JS
        assert 'window.clusterRefresh' in SUPERVISOR_JS

    def test_add_node_actually_registers(self):
        assert "fetch('/api/cluster/nodes/join'" in SUPERVISOR_JS
        # The old handler only showed a delayed success toast.
        assert 'Edge Node verified & joined cluster mesh' not in SUPERVISOR_CODE

    def test_scan_no_longer_fabricates_a_subnet_sweep(self):
        for fiction in (
            'Scanned 254 local LAN addresses',
            'Broadcasting discovery ping',
            'Handshake latency verified under 3ms',
        ):
            assert fiction not in SUPERVISOR_CODE
        assert "fetch('/api/cluster/status')" in SUPERVISOR_JS

    def test_rebalance_uses_real_dispatch(self):
        assert "fetch('/api/cluster/dispatch'" in SUPERVISOR_JS
        # The old handler announced invented load percentages.
        assert 'Master 40%, Edge M2 35%' not in SUPERVISOR_CODE

    def test_dispatch_sends_the_field_the_api_requires(self):
        # ClusterDispatchRequest requires task_prompt; task_type would 422.
        assert 'task_prompt' in SUPERVISOR_JS

    def test_cluster_view_refreshes_when_opened(self):
        assert 'if (typeof window.clusterRefresh === \'function\') window.clusterRefresh();' in SUPERVISOR_JS
