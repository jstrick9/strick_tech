"""
Notion Connector — Full Live Verification Tests
Tests all 19 capabilities via the platform API (POST /api/connectors/conn_notion/execute)
Credentials are stored in DB; no raw secrets in assertions.

Database: 39d47985-dffc-807a-8916-cab55644cf84  (test DB in David's Space)
Parent page: 39d47985-dffc-8016-98e8-c39cda4af1f9
"""
import pytest
import httpx
import time

BASE = "http://127.0.0.1:8787"
CONNECTOR = "conn_notion"

# Known IDs from the Notion workspace
TEST_DB_ID    = "39d47985-dffc-807a-8916-cab55644cf84"
PARENT_PAGE_ID = "39d47985-dffc-8016-98e8-c39cda4af1f9"

# Storage for IDs created during tests (shared across test session)
_state: dict = {}


def execute(action: str, payload: dict = None) -> dict:
    """Helper: call the platform execute endpoint."""
    body = {"action": action, "payload": payload or {}, "agent_id": "test_agent"}
    r = httpx.post(f"{BASE}/api/connectors/{CONNECTOR}/execute", json=body, timeout=30)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Connection & Bot Info
# ─────────────────────────────────────────────────────────────────────────────

class TestConnection:
    def test_01_test_connection(self):
        """Verify API token works and bot identity is returned."""
        res = execute("test_connection")
        assert res["ok"] is True, res
        assert res["bot_name"] == "Agentic OS"
        assert "bot_id" in res
        assert res["workspace_name"] == "David\u2019s Space"
        print(f"\n  ✅ Bot: {res['bot_name']} | Workspace: {res['workspace_name']} | Owner: {res.get('owner_email')}")

    def test_02_get_bot_info(self):
        """Full bot info object."""
        res = execute("get_bot_info")
        assert res["ok"] is True, res
        bot = res["bot"]
        assert bot["object"] == "user"
        assert bot["type"] == "bot"
        assert bot["name"] == "Agentic OS"
        print(f"\n  ✅ bot_id={bot['id']}")

    def test_03_list_users(self):
        """List workspace users. PATs return bot-only due to Notion restriction; connector handles gracefully."""
        res = execute("list_users")
        assert res["ok"] is True, res
        assert isinstance(res["users"], list)
        # PATs cannot list all users — connector returns bot user + note
        if res.get("note"):
            assert len(res["users"]) >= 1  # at minimum the bot itself
            print(f"\n  ✅ {len(res['users'])} user(s) (PAT restriction: bot only) | note={res['note'][:60]}")
        else:
            print(f"\n  ✅ {len(res['users'])} user(s) found, has_more={res['has_more']}")

    def test_04_search_all(self):
        """Search returns accessible pages/databases."""
        res = execute("search", {"page_size": 10})
        assert res["ok"] is True, res
        assert isinstance(res["results"], list)
        assert len(res["results"]) >= 1  # at least the test DB and its parent page
        types = [r["object"] for r in res["results"]]
        print(f"\n  ✅ {len(res['results'])} results: {set(types)}")

    def test_05_search_filter_databases(self):
        """Search filtered to databases only."""
        res = execute("search", {
            "filter": {"value": "database", "property": "object"},
            "page_size": 5
        })
        assert res["ok"] is True, res
        dbs = res["results"]
        assert len(dbs) >= 1
        for db in dbs:
            assert db["object"] == "database"
        print(f"\n  ✅ {len(dbs)} database(s) found")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Database Operations
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabase:
    def test_06_get_database(self):
        """Retrieve the test database metadata."""
        res = execute("get_database", {"database_id": TEST_DB_ID})
        assert res["ok"] is True, res
        assert res["id"].replace("-", "") == TEST_DB_ID.replace("-", "")
        assert "Name" in res["properties"]
        assert res["url"] is not None
        print(f"\n  ✅ DB id={res['id']} | props={res['properties']}")

    def test_07_query_database_empty(self):
        """Query the database (may be empty initially)."""
        res = execute("query_database", {"database_id": TEST_DB_ID, "page_size": 10})
        assert res["ok"] is True, res
        assert isinstance(res["results"], list)
        assert "has_more" in res
        print(f"\n  ✅ {res['count']} row(s) in database")

    def test_08_add_database_row_first(self):
        """Add a row to the database (creates a page inside it)."""
        res = execute("add_database_row", {
            "database_id": TEST_DB_ID,
            "title": "Agentic OS Test Row — 2026-07-14",
            "properties": {
                "Name": {
                    "title": [{"type": "text", "text": {"content": "Agentic OS Test Row — 2026-07-14"}}]
                }
            }
        })
        assert res["ok"] is True, res
        assert res["page_id"] is not None
        assert res["url"] is not None
        _state["row_page_id"] = res["page_id"]
        print(f"\n  ✅ Created row page_id={res['page_id']}")

    def test_09_add_database_row_second(self):
        """Add a second row so query_database returns >=2 results."""
        res = execute("add_database_row", {
            "database_id": TEST_DB_ID,
            "title": "Second Test Row",
            "properties": {
                "Name": {
                    "title": [{"type": "text", "text": {"content": "Second Test Row"}}]
                }
            }
        })
        assert res["ok"] is True, res
        _state["row_page_id_2"] = res["page_id"]
        print(f"\n  ✅ Created second row page_id={res['page_id']}")

    def test_10_query_database_with_rows(self):
        """After adding rows, query shows them."""
        res = execute("query_database", {"database_id": TEST_DB_ID})
        assert res["ok"] is True, res
        assert res["count"] >= 2
        # Verify title extraction works
        titles = [r["title"] for r in res["results"]]
        assert any("Agentic OS Test Row" in t for t in titles), f"Expected test row in {titles}"
        print(f"\n  ✅ {res['count']} rows; titles: {titles}")

    def test_11_query_database_sorted(self):
        """Query with sort by created_time descending."""
        res = execute("query_database", {
            "database_id": TEST_DB_ID,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 5
        })
        assert res["ok"] is True, res
        assert res["count"] >= 1
        print(f"\n  ✅ Sorted query: {res['count']} rows")

    def test_12_update_database_row(self):
        """Update a row's Name property."""
        row_id = _state.get("row_page_id")
        assert row_id, "row_page_id not set — test_08 must pass first"
        res = execute("update_database_row", {
            "page_id": row_id,
            "properties": {
                "Name": {
                    "title": [{"type": "text", "text": {"content": "Agentic OS Test Row — UPDATED ✅"}}]
                }
            }
        })
        assert res["ok"] is True, res
        assert res["page_id"] is not None
        print(f"\n  ✅ Row updated; last_edited={res['last_edited_time']}")

    def test_13_create_database(self):
        """Create a new child database under the parent page."""
        res = execute("create_database", {
            "parent_page_id": PARENT_PAGE_ID,
            "title": "Agentic OS Sub-Database",
            "properties": {
                "Name": {"title": {}},
            }
        })
        assert res["ok"] is True, res
        assert res["database_id"] is not None
        assert res["url"] is not None
        _state["new_db_id"] = res["database_id"]
        print(f"\n  ✅ New database created: id={res['database_id']}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Page Operations
# ─────────────────────────────────────────────────────────────────────────────

class TestPages:
    def test_14_create_page_under_parent(self):
        """Create a standalone page under the parent page."""
        res = execute("create_page", {
            "title": "Agentic OS Verification Page — 2026-07-14",
            "parent": {"page_id": PARENT_PAGE_ID},
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": "Agentic OS Verification Page — 2026-07-14"}}]
                }
            },
            "content": "This page was created by the Agentic OS connector verification suite on 2026-07-14."
        })
        assert res["ok"] is True, res
        assert res["page_id"] is not None
        assert res["url"] is not None
        _state["page_id"] = res["page_id"]
        print(f"\n  ✅ Page created: id={res['page_id']} | url={res['url']}")

    def test_15_get_page(self):
        """Retrieve the created page metadata."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        res = execute("get_page", {"page_id": page_id})
        assert res["ok"] is True, res
        assert res["id"] is not None
        assert res["archived"] is False
        print(f"\n  ✅ Page retrieved: id={res['id']} | title='{res['title']}'")

    def test_16_get_page_content(self):
        """Retrieve the blocks/content of the created page."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        res = execute("get_page_content", {"page_id": page_id})
        assert res["ok"] is True, res
        assert isinstance(res["blocks"], list)
        assert res["block_count"] >= 1
        assert "Agentic OS connector" in res["text_content"]
        print(f"\n  ✅ {res['block_count']} block(s); text='{res['text_content'][:80]}'")

    def test_17_append_page_content(self):
        """Append a paragraph block to the created page."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        res = execute("append_page_content", {
            "page_id": page_id,
            "text": "Appended by append_page_content action ✅ — 2026-07-14"
        })
        assert res["ok"] is True, res
        assert res["appended_blocks"] >= 1
        print(f"\n  ✅ Appended {res['appended_blocks']} block(s) to page")

    def test_18_get_page_content_after_append(self):
        """Verify appended content is visible."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        res = execute("get_page_content", {"page_id": page_id})
        assert res["ok"] is True, res
        assert res["block_count"] >= 2  # original + appended
        assert "Appended" in res["text_content"]
        print(f"\n  ✅ {res['block_count']} blocks after append; content verified")

    def test_19_get_block(self):
        """Get a specific block from the page."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        # Get the blocks first
        content_res = execute("get_page_content", {"page_id": page_id})
        assert content_res["ok"] is True
        blocks = content_res["blocks"]
        assert len(blocks) >= 1
        block_id = blocks[0]["id"]
        _state["block_id"] = block_id

        res = execute("get_block", {"block_id": block_id})
        assert res["ok"] is True, res
        assert res["block"]["id"] == block_id
        print(f"\n  ✅ Block retrieved: id={block_id} type={res['block']['type']}")

    def test_20_append_heading_and_bullets(self):
        """Append rich content: heading + bullet list."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Test Results Summary"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "✅ test_connection passed"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "✅ create_page passed"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "✅ append_page_content passed"}}]
                }
            }
        ]
        res = execute("append_page_content", {"page_id": page_id, "children": children})
        assert res["ok"] is True, res
        assert res["appended_blocks"] == 4
        print(f"\n  ✅ Appended heading + 3 bullets")

    def test_21_update_page_icon(self):
        """Update the page icon (emoji)."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        res = execute("update_page", {
            "page_id": page_id,
            "icon": {"type": "emoji", "emoji": "🤖"}
        })
        assert res["ok"] is True, res
        print(f"\n  ✅ Page icon set to 🤖")

    def test_22_delete_block(self):
        """Delete a block from the page (soft-delete)."""
        block_id = _state.get("block_id")
        assert block_id, "block_id not set — test_19 must pass first"
        res = execute("delete_block", {"block_id": block_id})
        assert res["ok"] is True, res
        assert res["deleted_block_id"] == block_id
        print(f"\n  ✅ Block {block_id} deleted")

    def test_23_archive_row_page(self):
        """Archive (soft-delete) the second test row page."""
        page_id = _state.get("row_page_id_2")
        assert page_id, "row_page_id_2 not set — test_09 must pass first"
        res = execute("archive_page", {"page_id": page_id})
        assert res["ok"] is True, res
        assert res["archived"] is True
        print(f"\n  ✅ Page {page_id} archived")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Comments
# ─────────────────────────────────────────────────────────────────────────────

class TestComments:
    def test_24_create_comment(self):
        """Create a comment on the verification page."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        res = execute("create_comment", {
            "page_id": page_id,
            "text": "Automated comment from Agentic OS connector verification ✅"
        })
        # Comments may require special scope — accept 403 with helpful message
        if not res["ok"] and res.get("status_code") == 403:
            pytest.skip(f"Comments scope not enabled: {res['error']}")
        assert res["ok"] is True, res
        assert res["comment_id"] is not None
        _state["comment_id"] = res["comment_id"]
        print(f"\n  ✅ Comment created: id={res['comment_id']}")

    def test_25_list_comments(self):
        """List comments on the verification page."""
        page_id = _state.get("page_id")
        assert page_id, "page_id not set — test_14 must pass first"
        res = execute("list_comments", {"page_id": page_id})
        if not res["ok"] and res.get("status_code") == 403:
            pytest.skip(f"Comments scope not enabled: {res['error']}")
        assert res["ok"] is True, res
        assert isinstance(res["comments"], list)
        print(f"\n  ✅ {len(res['comments'])} comment(s)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Search with text filter
# ─────────────────────────────────────────────────────────────────────────────

class TestSearch:
    def test_26_search_with_query(self):
        """Search for pages containing 'Agentic OS'."""
        res = execute("search", {"query": "Agentic OS", "page_size": 10})
        assert res["ok"] is True, res
        results = res["results"]
        assert len(results) >= 1
        ids = [r["id"] for r in results]
        print(f"\n  ✅ Found {len(results)} result(s) matching 'Agentic OS'")

    def test_27_search_filter_pages(self):
        """Search filtered to pages only."""
        res = execute("search", {
            "filter": {"value": "page", "property": "object"},
            "page_size": 10
        })
        assert res["ok"] is True, res
        for r in res["results"]:
            assert r["object"] == "page"
        print(f"\n  ✅ {len(res['results'])} page(s) found via filtered search")
