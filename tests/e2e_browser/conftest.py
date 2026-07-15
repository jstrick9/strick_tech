"""Browser E2E test configuration — uses real Playwright Chromium."""
import pytest
from playwright.sync_api import sync_playwright, Page, Browser

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        yield b
        b.close()

@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    pg  = ctx.new_page()
    yield pg
    ctx.close()
