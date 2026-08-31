"""Gap #013: bounty_hunter scan_id not sanitized (path traversal read/write).

get_bounty_scan / execute_autopatch built `SCANS_DIR / f'{scan_id}.json'` from
the URL path parameter, so a caller-supplied traversal payload would escape the
scans directory to read (or, via autopatch, overwrite) an arbitrary .json file.
FastAPI's routing currently rejects encoded slashes so it is not yet reachable
through HTTP, but the read path must be hardened the same way workflow._wf_path
is — a route/mount change would otherwise expose it. Sanitized now.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers import bounty_hunter as bh
from backend.services.safe_paths import is_within


class TestBountyScanPathSafety:
    def test_traversal_payloads_stay_within_scans_dir(self):
        for bad in ('../secret_test', 'a/../../etc/passwd', '..\\evil', '/etc/passwd', '....//'):
            p = bh._scan_file(bad).resolve()
            assert is_within(p, bh.SCANS_DIR.resolve()), f'{bad!r} escaped scans dir'

    def test_safe_id_preserved(self):
        assert bh._safe_scan_id('bh_scan_ok123') == 'bh_scan_ok123'
        assert bh._safe_scan_id('scan-ABC_123') == 'scan-ABC_123'

    def test_slashes_and_separators_stripped_to_bare_stem(self):
        assert '/' not in bh._safe_scan_id('a/b')
        assert '\\' not in bh._safe_scan_id('a\\b')
        # no residual path separator survives into the joined filename
        joined = str(bh._scan_file('a/../../etc/passwd'))
        assert '/..' not in joined and '..' not in Path(joined).name

    def test_max_len_capped(self):
        assert len(bh._safe_scan_id('x' * 500)) <= 128

    def test_read_endpoint_not_reachable_traversal_through_http(self, client):
        # Route normalization rejects encoded separators; a genuine scan still 404s
        # as an unknown id that does not escape (defense regression guard).
        r = client.get('/api/bounty/scans/..%2Fetc%2Fpasswd')
        assert r.status_code in (404, 422)
