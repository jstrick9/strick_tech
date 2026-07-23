"""Audit chain concurrency regression coverage."""
from concurrent.futures import ThreadPoolExecutor

from backend.routers.audit_log import append_entry, verify_chain


def test_audit_append_serializes_concurrent_writers():
    def write(i):
        return append_entry('concurrency', 'Concurrency Test', 'test_action', f'entry {i}')

    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(write, range(24)))
    assert len({entry['entry_id'] for entry in entries}) == 24
    result = verify_chain()
    assert result['ok'] is True
    assert result['verified'] >= 24
