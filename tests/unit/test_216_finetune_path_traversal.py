"""Gap #021: finetune dataset_id/job_id used in file paths without sanitizing.

create_finetune_dataset / start_finetune_job / get_finetune_job /
export_lora_adapter built paths with the user-supplied id, which could contain
`../`, a path separator, or an absolute path — escaping DATASETS_DIR/JOBS_DIR to
write or read an arbitrary .json/.jsonl (verified: an absolute dataset_id wrote
outside DATASETS_DIR). The export_format was also echoed into a filename
suffix. IDs are now reduced to a bare safe stem and export_format allow-listed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers.finetune import DATASETS_DIR, JOBS_DIR, _safe_stem
from backend.services.safe_paths import is_within


class TestFinetuneIdSanitization:
    def test_traversal_payloads_become_safe_stems(self):
        for bad in ('../evil', '/etc/passwd', 'a/../../x', '..\\win', 'x.lock', '../../tmp/evil'):
            stem = _safe_stem(bad)
            assert '/' not in stem and '\\' not in stem
            assert not stem.startswith('..')
            # both read/write paths now stay in their directory
            p = (DATASETS_DIR / f'{stem}.jsonl').resolve()
            j = (JOBS_DIR / f'{stem}.json').resolve()
            assert is_within(p, DATASETS_DIR.resolve())
            assert is_within(j, JOBS_DIR.resolve())

    def test_idempotent_clean_id(self):
        assert _safe_stem('ds_AbC-123') == 'ds_abc-123'

    def test_empty_falls_back(self):
        s = _safe_stem('') or ''
        assert s and '/' not in s and '\\' not in s

    def test_allowed_export_formats_enum(self):
        from backend.routers import finetune as ft
        assert {'safetensors', 'gguf', 'ggml', 'bin'} <= ft._ALLOWED_EXPORT_FORMATS
