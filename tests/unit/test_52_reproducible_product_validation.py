"""The browser validation environment must be reproducible from a clean machine."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_test_requirements_include_browser_runner():
    text = (ROOT / 'requirements-test.txt').read_text(encoding='utf-8')
    assert '-r requirements.txt' in text
    assert 'playwright==' in text
    assert 'pytest' in text


def test_validation_script_bootstraps_browser_and_runs_product_gates():
    text = (ROOT / 'scripts' / 'run_product_validation.sh').read_text(encoding='utf-8')
    assert 'playwright install --with-deps chromium' in text
    assert 'node --check' in text
    assert 'tests/e2e/test_product_experience_live.py' in text
