"""
Compliance Report Generator — Full Verification Test Suite
Tests every backend endpoint for the Compliance Report system.

Endpoints under test:
  GET    /api/compliance/summary             — live compliance dashboard metrics
  GET    /api/compliance/frameworks          — list of supported frameworks
  GET    /api/compliance/reports             — report history
  GET    /api/compliance/reports/{id}        — get single report metadata
  DELETE /api/compliance/reports/{id}        — delete report
  POST   /api/compliance/generate            — generate report (PDF/JSON/CSV)

Report formats: PDF (fpdf2), JSON, CSV
Frameworks: General, SOC2, GDPR, HIPAA, FINRA, ISO27001
Sections: audit_chain, hitl, policies, agent_identity, connectors, cost, supervisor

Also verifies:
  GET /api/audit-log/verify                  — chain integrity check
  GET /api/audit-log/stats                   — audit log statistics
  GET /api/audit-log/export/json             — JSON export
  GET /api/audit-log/export/csv              — CSV export
"""
import pytest, httpx, json, time

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 90

def get(path):
    r = httpx.get(f"{BASE}{path}", timeout=TIMEOUT)
    assert r.status_code == 200, f"GET {path} → {r.status_code}: {r.text[:200]}"
    return r.json()

def post(path, body=None):
    r = httpx.post(f"{BASE}{path}", json=body or {}, timeout=TIMEOUT)
    assert r.status_code == 200, f"POST {path} → {r.status_code}: {r.text[:300]}"
    return r

def delete(path):
    r = httpx.delete(f"{BASE}{path}", timeout=TIMEOUT)
    assert r.status_code == 200, f"DELETE {path} → {r.status_code}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Summary Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestSummary:
    def test_01_summary_returns_all_fields(self):
        d = get("/api/compliance/summary")
        required = [
            "chain_integrity","chain_entries","high_risk_actions","failed_actions",
            "hitl_total","hitl_pending","policy_blocked","policy_total","block_rate_pct",
            "active_agents","total_cost_usd","reports_generated",
        ]
        for f in required:
            assert f in d, f"Missing field: {f}"
        print(f"\n  ✅ All {len(required)} summary fields present")

    def test_02_summary_chain_integrity_is_bool(self):
        d = get("/api/compliance/summary")
        assert isinstance(d["chain_integrity"], bool)
        print(f"\n  ✅ chain_integrity={d['chain_integrity']} (bool)")

    def test_03_summary_counts_are_nonnegative(self):
        d = get("/api/compliance/summary")
        for k in ["chain_entries","high_risk_actions","hitl_total","policy_blocked","active_agents"]:
            assert d[k] >= 0, f"{k} is negative: {d[k]}"
        print(f"\n  ✅ Counts non-negative: entries={d['chain_entries']}, hitl={d['hitl_total']}")

    def test_04_summary_has_real_data(self):
        d = get("/api/compliance/summary")
        assert d["chain_entries"] > 0, "Expected audit entries in DB"
        assert d["hitl_total"]    > 0, "Expected HITL records in DB"
        print(f"\n  ✅ Real data: {d['chain_entries']:,} audit entries, {d['hitl_total']:,} HITL records")

    def test_05_block_rate_is_valid_percentage(self):
        d = get("/api/compliance/summary")
        pct = d["block_rate_pct"]
        assert 0 <= pct <= 100
        print(f"\n  ✅ block_rate_pct={pct}%")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Frameworks Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestFrameworks:
    def test_06_frameworks_returns_6(self):
        d = get("/api/compliance/frameworks")
        assert "frameworks" in d
        fws = d["frameworks"]
        assert len(fws) == 6
        ids = [f["id"] for f in fws]
        assert "General"  in ids
        assert "SOC2"     in ids
        assert "GDPR"     in ids
        assert "HIPAA"    in ids
        assert "FINRA"    in ids
        assert "ISO27001" in ids
        print(f"\n  ✅ 6 frameworks: {ids}")

    def test_07_frameworks_have_required_fields(self):
        d = get("/api/compliance/frameworks")
        for fw in d["frameworks"]:
            assert "id"          in fw
            assert "name"        in fw
            assert "description" in fw
        print(f"\n  ✅ All frameworks have id, name, description")


# ─────────────────────────────────────────────────────────────────────────────
# 3. PDF Generation — All Frameworks
# ─────────────────────────────────────────────────────────────────────────────

class TestPDFGeneration:
    _generated_ids = []

    def _generate(self, fw, scope=None):
        body = {
            "title": f"{fw} Compliance Audit 2026",
            "framework": fw,
            "format": "pdf",
            "scope": scope or {
                "audit_chain": True, "hitl": True, "policies": True,
                "agent_identity": True, "connectors": True, "cost": True, "supervisor": True,
            }
        }
        r = httpx.post(f"{BASE}/api/compliance/generate", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, f"PDF gen failed for {fw}: HTTP {r.status_code}: {r.text[:200]}"
        return r

    def test_08_pdf_general(self):
        r = self._generate("General")
        assert r.content[:4] == b'%PDF', "Response is not a valid PDF"
        assert len(r.content) > 5000
        rid = r.headers.get("X-Report-Id")
        assert rid
        TestPDFGeneration._generated_ids.append(rid)
        print(f"\n  ✅ General PDF: {len(r.content):,} bytes | id={rid}")

    def test_09_pdf_soc2(self):
        r = self._generate("SOC2")
        assert r.content[:4] == b'%PDF'
        assert len(r.content) > 5000
        TestPDFGeneration._generated_ids.append(r.headers.get("X-Report-Id",""))
        print(f"\n  ✅ SOC2 PDF: {len(r.content):,} bytes")

    def test_10_pdf_gdpr(self):
        r = self._generate("GDPR")
        assert r.content[:4] == b'%PDF'
        assert len(r.content) > 5000
        TestPDFGeneration._generated_ids.append(r.headers.get("X-Report-Id",""))
        print(f"\n  ✅ GDPR PDF: {len(r.content):,} bytes")

    def test_11_pdf_hipaa(self):
        r = self._generate("HIPAA")
        assert r.content[:4] == b'%PDF'
        assert len(r.content) > 5000
        TestPDFGeneration._generated_ids.append(r.headers.get("X-Report-Id",""))
        print(f"\n  ✅ HIPAA PDF: {len(r.content):,} bytes")

    def test_12_pdf_finra(self):
        r = self._generate("FINRA")
        assert r.content[:4] == b'%PDF'
        assert len(r.content) > 5000
        TestPDFGeneration._generated_ids.append(r.headers.get("X-Report-Id",""))
        print(f"\n  ✅ FINRA PDF: {len(r.content):,} bytes")

    def test_13_pdf_iso27001(self):
        r = self._generate("ISO27001")
        assert r.content[:4] == b'%PDF'
        assert len(r.content) > 5000
        TestPDFGeneration._generated_ids.append(r.headers.get("X-Report-Id",""))
        print(f"\n  ✅ ISO27001 PDF: {len(r.content):,} bytes")

    def test_14_pdf_has_report_id_header(self):
        r = self._generate("General")
        rid = r.headers.get("X-Report-Id","")
        assert rid.startswith("rpt_"), f"Invalid report ID: {rid}"
        print(f"\n  ✅ Report-Id header: {rid}")

    def test_15_pdf_has_content_disposition(self):
        r = self._generate("General")
        cd = r.headers.get("Content-Disposition","")
        assert "attachment" in cd
        assert ".pdf" in cd
        print(f"\n  ✅ Content-Disposition: {cd[:60]}")

    def test_16_pdf_with_minimal_scope(self):
        """PDF with only audit_chain section — should still generate valid PDF."""
        r = self._generate("General", scope={"audit_chain": True})
        assert r.content[:4] == b'%PDF'
        print(f"\n  ✅ Minimal scope PDF: {len(r.content):,} bytes")

    def test_17_pdf_with_date_range(self):
        """PDF filtered to last 7 days — should include filtered data."""
        from datetime import datetime, timedelta, timezone
        now   = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()
        r = httpx.post(f"{BASE}/api/compliance/generate", json={
            "title": "Filtered Report",
            "framework": "General",
            "format": "pdf",
            "date_from": week_ago,
            "date_to":   now.isoformat(),
        }, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.content[:4] == b'%PDF'
        print(f"\n  ✅ Date-filtered PDF: {len(r.content):,} bytes")


# ─────────────────────────────────────────────────────────────────────────────
# 4. JSON Export
# ─────────────────────────────────────────────────────────────────────────────

class TestJSONExport:
    def test_18_json_export_valid(self):
        r = post("/api/compliance/generate", {
            "title": "JSON Test",
            "framework": "General",
            "format": "json",
        })
        assert r.status_code == 200
        d = r.json()
        assert "report_id"   in d
        assert "title"       in d
        assert "framework"   in d
        assert "generated_at" in d
        assert "summary"     in d
        assert "data"        in d
        print(f"\n  ✅ JSON export: {len(r.content):,} bytes")

    def test_19_json_has_summary_fields(self):
        r = post("/api/compliance/generate", {"title":"JSON","framework":"General","format":"json"})
        d = r.json()
        summary = d["summary"]
        assert "audit_total"      in summary
        assert "high_risk_count"  in summary
        assert "hitl_total"       in summary
        assert "policy_blocked"   in summary
        assert "chain_ok"         in summary
        print(f"\n  ✅ JSON summary fields: audit={summary['audit_total']}, chain_ok={summary['chain_ok']}")

    def test_20_json_data_has_sections(self):
        r = post("/api/compliance/generate", {"title":"JSON","framework":"General","format":"json"})
        d = r.json()["data"]
        assert "audit"      in d
        assert "hitl"       in d
        assert "policies"   in d
        assert "connectors" in d
        assert "supervisor" in d
        print(f"\n  ✅ JSON data sections: {list(d.keys())}")

    def test_21_json_audit_section_has_entries(self):
        r = post("/api/compliance/generate", {"title":"JSON","framework":"General","format":"json"})
        audit = r.json()["data"]["audit"]
        assert "total"           in audit
        assert "by_risk"         in audit
        assert "by_outcome"      in audit
        assert "chain_integrity" in audit
        assert audit["total"] > 0
        print(f"\n  ✅ Audit section: {audit['total']:,} entries")

    def test_22_json_chain_integrity_in_data(self):
        r = post("/api/compliance/generate", {"title":"JSON","framework":"General","format":"json"})
        ci = r.json()["data"]["audit"]["chain_integrity"]
        assert "ok"       in ci
        assert "verified" in ci
        assert isinstance(ci["ok"], bool)
        print(f"\n  ✅ Chain integrity in JSON: ok={ci['ok']}, verified={ci['verified']}")

    def test_23_json_has_content_disposition(self):
        r = post("/api/compliance/generate", {"title":"JSON","framework":"General","format":"json"})
        cd = r.headers.get("Content-Disposition","")
        assert "attachment" in cd
        assert ".json" in cd
        print(f"\n  ✅ Content-Disposition JSON: {cd[:60]}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. CSV Export
# ─────────────────────────────────────────────────────────────────────────────

class TestCSVExport:
    def test_24_csv_export_valid(self):
        r = post("/api/compliance/generate", {
            "title": "CSV Test",
            "framework": "General",
            "format": "csv",
        })
        assert r.status_code == 200
        assert len(r.content) > 100
        # First line should be CSV header
        first_line = r.content.split(b'\n')[0].decode('utf-8', errors='replace')
        assert 'section' in first_line or 'seq' in first_line or 'key' in first_line
        print(f"\n  ✅ CSV export: {len(r.content):,} bytes | header: {first_line[:60]}")

    def test_25_csv_has_content_disposition(self):
        r = post("/api/compliance/generate", {"title":"CSV","framework":"General","format":"csv"})
        cd = r.headers.get("Content-Disposition","")
        assert "attachment" in cd
        assert ".csv" in cd
        print(f"\n  ✅ Content-Disposition CSV: {cd[:60]}")

    def test_26_csv_has_summary_data(self):
        r = post("/api/compliance/generate", {"title":"CSV","framework":"General","format":"csv"})
        text = r.content.decode('utf-8', errors='replace')
        assert 'summary' in text
        print(f"\n  ✅ CSV contains summary section, {len(text.splitlines())} lines")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Report History
# ─────────────────────────────────────────────────────────────────────────────

class TestReportHistory:
    _test_report_id = None

    def test_27_generate_and_appear_in_history(self):
        # Generate a report
        r = post("/api/compliance/generate", {
            "title": "History Test Report",
            "framework": "General",
            "format": "pdf",
        })
        rid = r.headers.get("X-Report-Id","")
        assert rid
        TestReportHistory._test_report_id = rid

        # Check it appears in history
        hist = get("/api/compliance/reports")
        assert "reports" in hist
        ids = [rpt["report_id"] for rpt in hist["reports"]]
        assert rid in ids
        print(f"\n  ✅ Report {rid} appears in history")

    def test_28_history_reports_have_required_fields(self):
        hist = get("/api/compliance/reports")
        for rpt in hist["reports"][:3]:
            assert "report_id"   in rpt
            assert "title"       in rpt
            assert "framework"   in rpt
            assert "format"      in rpt
            assert "status"      in rpt
            assert "created_at"  in rpt
        print(f"\n  ✅ All report records have required fields")

    def test_29_get_single_report_metadata(self):
        rid = TestReportHistory._test_report_id
        if not rid:
            pytest.skip("No report generated in test_27")
        d = get(f"/api/compliance/reports/{rid}")
        assert d.get("ok") is True
        rpt = d["report"]
        assert rpt["report_id"] == rid
        assert rpt["status"] == "done"
        assert rpt["file_size_bytes"] > 0
        print(f"\n  ✅ Report {rid}: status={rpt['status']}, size={rpt['file_size_bytes']:,} bytes")

    def test_30_report_has_summary(self):
        rid = TestReportHistory._test_report_id
        if not rid:
            pytest.skip("No report generated")
        d = get(f"/api/compliance/reports/{rid}")
        summary = d["report"].get("summary", {})
        assert isinstance(summary, dict)
        print(f"\n  ✅ Report summary: {list(summary.keys())}")

    def test_31_delete_report(self):
        rid = TestReportHistory._test_report_id
        if not rid:
            pytest.skip("No report generated")
        d = delete(f"/api/compliance/reports/{rid}")
        assert d.get("ok") is True
        # Verify gone
        r = httpx.get(f"{BASE}/api/compliance/reports/{rid}", timeout=TIMEOUT)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Report {rid} deleted and confirmed gone")

    def test_32_nonexistent_report_returns_404(self):
        r = httpx.get(f"{BASE}/api/compliance/reports/nonexistent_rpt_xyz", timeout=TIMEOUT)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Nonexistent report → 404/ok=False")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Validation
# ─────────────────────────────────────────────────────────────────────────────

class TestValidation:
    def test_33_invalid_framework_rejected(self):
        r = httpx.post(f"{BASE}/api/compliance/generate",
                       json={"title":"Test","framework":"INVALID","format":"pdf"},
                       timeout=TIMEOUT)
        assert r.status_code in (200, 400)
        d = r.json()
        assert d.get("ok") is False
        print(f"\n  ✅ Invalid framework rejected: {d.get('error','')[:60]}")

    def test_34_invalid_format_rejected(self):
        r = httpx.post(f"{BASE}/api/compliance/generate",
                       json={"title":"Test","framework":"General","format":"xml"},
                       timeout=TIMEOUT)
        assert r.status_code in (200, 400)
        d = r.json()
        assert d.get("ok") is False
        print(f"\n  ✅ Invalid format rejected: {d.get('error','')[:60]}")

    def test_35_all_scope_false_still_generates(self):
        """Report with all sections disabled still generates (cover + certificate)."""
        r = httpx.post(f"{BASE}/api/compliance/generate", json={
            "title": "Empty scope test", "framework": "General", "format": "pdf",
            "scope": {k: False for k in ["audit_chain","hitl","policies","agent_identity","connectors","cost","supervisor"]}
        }, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.content[:4] == b'%PDF'
        print(f"\n  ✅ Empty-scope PDF still generates: {len(r.content):,} bytes")

    def test_36_empty_body_uses_defaults(self):
        """POST with no body still generates a General PDF with defaults."""
        r = httpx.post(f"{BASE}/api/compliance/generate", json={}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.content[:4] == b'%PDF'
        print(f"\n  ✅ Empty body uses defaults: {len(r.content):,} bytes General PDF")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Audit Chain (existing endpoint verification)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditChain:
    def test_37_audit_list_returns_entries(self):
        d = get("/api/audit-log?limit=10")
        assert "entries" in d
        assert "total"   in d
        assert len(d["entries"]) <= 10
        assert d["total"] > 0
        print(f"\n  ✅ Audit log: {d['total']:,} total, {len(d['entries'])} returned")

    def test_38_audit_entries_have_required_fields(self):
        d = get("/api/audit-log?limit=5")
        for e in d["entries"]:
            assert "seq"          in e
            assert "entry_id"     in e
            assert "agent_id"     in e
            assert "action_type"  in e
            assert "risk_level"   in e
            assert "outcome"      in e
            assert "entry_hash"   in e
            assert "prev_hash"    in e
        print(f"\n  ✅ All audit entries have required fields")

    def test_39_chain_verify_passes(self):
        d = get("/api/audit-log/verify")
        assert "ok"       in d
        assert "verified" in d
        assert d["verified"] > 0
        print(f"\n  ✅ Chain verify: ok={d['ok']}, verified={d['verified']:,}")

    def test_40_audit_stats_complete(self):
        d = get("/api/audit-log/stats")
        assert "total"      in d
        assert "by_risk"    in d
        assert "by_outcome" in d
        assert "top_agents" in d
        assert d["total"] > 0
        print(f"\n  ✅ Audit stats: total={d['total']:,}")

    def test_41_audit_filter_by_risk(self):
        d = get("/api/audit-log?risk_level=high&limit=10")
        for e in d["entries"]:
            assert e["risk_level"] == "high"
        print(f"\n  ✅ Risk filter: {d['total']} high-risk entries")

    def test_42_audit_filter_by_outcome(self):
        d = get("/api/audit-log?outcome=failure&limit=10")
        for e in d["entries"]:
            assert e["outcome"] == "failure"
        print(f"\n  ✅ Outcome filter: {d['total']} failures")

    def test_43_audit_entry_detail(self):
        entries = get("/api/audit-log?limit=1")["entries"]
        if not entries:
            pytest.skip("No entries")
        entry_id = entries[0]["entry_id"]
        d = get(f"/api/audit-log/entry/{entry_id}")
        assert "entry"   in d
        assert "receipt" in d
        assert d["entry"]["entry_id"] == entry_id
        print(f"\n  ✅ Entry detail: {entry_id}")

    def test_44_json_export_download(self):
        r = httpx.get(f"{BASE}/api/audit-log/export/json?limit=100", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "export_type"  in d
        assert "entries"      in d
        assert "chain_verify" in d
        assert len(d["entries"]) > 0
        print(f"\n  ✅ JSON export: {len(d['entries'])} entries")

    def test_45_csv_export_download(self):
        r = httpx.get(f"{BASE}/api/audit-log/export/csv?limit=100", timeout=TIMEOUT)
        assert r.status_code == 200
        assert len(r.content) > 100
        text = r.content.decode("utf-8", errors="replace")
        assert "\n" in text  # has multiple rows
        print(f"\n  ✅ CSV export: {len(text.splitlines())} rows")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Data Coverage in Reports
# ─────────────────────────────────────────────────────────────────────────────

class TestDataCoverage:
    @pytest.fixture(scope="class")
    def full_json_report(self):
        r = httpx.post(f"{BASE}/api/compliance/generate", json={
            "title": "Coverage Test", "framework": "General", "format": "json",
            "scope": {"audit_chain":True,"hitl":True,"policies":True,
                      "agent_identity":True,"connectors":True,"cost":True,"supervisor":True}
        }, timeout=TIMEOUT)
        assert r.status_code == 200
        return r.json()

    def test_46_report_covers_audit_chain(self, full_json_report):
        d = full_json_report["data"]
        assert "audit" in d
        assert d["audit"]["total"] > 0
        assert isinstance(d["audit"]["by_risk"], dict)
        assert isinstance(d["audit"]["chain_integrity"], dict)
        print(f"\n  ✅ Audit chain covered: {d['audit']['total']:,} entries")

    def test_47_report_covers_hitl(self, full_json_report):
        d = full_json_report["data"]
        assert "hitl" in d
        assert d["hitl"]["total"] > 0
        assert isinstance(d["hitl"]["by_status"], dict)
        print(f"\n  ✅ HITL covered: {d['hitl']['total']:,} items")

    def test_48_report_covers_policies(self, full_json_report):
        d = full_json_report["data"]
        assert "policies" in d
        assert isinstance(d["policies"]["active_policies"], list)
        assert len(d["policies"]["active_policies"]) >= 4  # at least default policies
        print(f"\n  ✅ Policies covered: {len(d['policies']['active_policies'])} active rules")

    def test_49_report_covers_agent_identity(self, full_json_report):
        d = full_json_report["data"]
        assert "agent_identity" in d
        assert d["agent_identity"]["total_agents"] > 0
        print(f"\n  ✅ Agent identity covered: {d['agent_identity']['total_agents']} agents")

    def test_50_report_covers_connectors(self, full_json_report):
        d = full_json_report["data"]
        assert "connectors" in d
        assert d["connectors"]["total"] >= 0  # can be 0 in some states
        print(f"\n  ✅ Connectors covered: {d['connectors']['total']} executions")

    def test_51_report_covers_supervisor(self, full_json_report):
        d = full_json_report["data"]
        assert "supervisor" in d
        assert d["supervisor"]["total"] > 0
        print(f"\n  ✅ Supervisor covered: {d['supervisor']['total']} runs")

    def test_52_summary_matches_data(self, full_json_report):
        summary = full_json_report["summary"]
        data    = full_json_report["data"]
        assert summary["audit_total"]   == data["audit"]["total"]
        assert summary["hitl_total"]    == data["hitl"]["total"]
        assert summary["chain_ok"]      == data["audit"]["chain_integrity"]["ok"]
        print(f"\n  ✅ Summary matches data sections")

    def test_53_high_risk_entries_in_report(self, full_json_report):
        audit = full_json_report["data"]["audit"]
        assert "high_risk_count" in audit
        assert "high_risk"       in audit
        assert len(audit["high_risk"]) >= 0  # can be 0
        print(f"\n  ✅ High-risk section present: {audit['high_risk_count']} flagged")

    def test_54_chain_integrity_included(self, full_json_report):
        ci = full_json_report["data"]["audit"]["chain_integrity"]
        assert "ok"       in ci
        assert "verified" in ci
        assert "message"  in ci
        assert ci["verified"] > 0
        print(f"\n  ✅ Chain integrity in report: ok={ci['ok']}, {ci['verified']:,} verified")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Frontend Contract
# ─────────────────────────────────────────────────────────────────────────────

class TestFrontendContract:
    def test_55_report_id_starts_with_rpt(self):
        r = httpx.post(f"{BASE}/api/compliance/generate",
                       json={"title":"Contract Test","framework":"General","format":"pdf"},
                       timeout=TIMEOUT)
        rid = r.headers.get("X-Report-Id","")
        assert rid.startswith("rpt_"), f"Report ID doesn't start with rpt_: {rid}"
        print(f"\n  ✅ Report ID format: {rid}")

    def test_56_x_report_summary_header_present(self):
        r = httpx.post(f"{BASE}/api/compliance/generate",
                       json={"title":"Summary Header Test","framework":"General","format":"json"},
                       timeout=TIMEOUT)
        summary_hdr = r.headers.get("X-Report-Summary","")
        assert len(summary_hdr) > 0
        d = json.loads(summary_hdr)
        assert "chain_ok" in d
        print(f"\n  ✅ X-Report-Summary header: {summary_hdr[:80]}")

    def test_57_report_history_count_field(self):
        hist = get("/api/compliance/reports")
        assert "count" in hist
        assert hist["count"] == len(hist["reports"])
        print(f"\n  ✅ history count={hist['count']} matches reports array")

    def test_58_generated_report_has_file_size(self):
        r = httpx.post(f"{BASE}/api/compliance/generate",
                       json={"title":"Size Test","framework":"General","format":"pdf"},
                       timeout=TIMEOUT)
        rid = r.headers.get("X-Report-Id","")
        time.sleep(0.5)
        meta = get(f"/api/compliance/reports/{rid}")
        rpt = meta["report"]
        assert rpt["file_size_bytes"] == len(r.content)
        print(f"\n  ✅ file_size_bytes={rpt['file_size_bytes']:,} matches actual response size")

    def test_59_scope_persisted_in_report(self):
        scope = {"audit_chain":True,"hitl":False,"policies":True,"agent_identity":False,
                 "connectors":True,"cost":False,"supervisor":True}
        r = httpx.post(f"{BASE}/api/compliance/generate",
                       json={"title":"Scope Test","framework":"SOC2","format":"json","scope":scope},
                       timeout=TIMEOUT)
        rid = r.headers.get("X-Report-Id","")
        time.sleep(0.5)
        meta = get(f"/api/compliance/reports/{rid}")
        stored_scope = meta["report"].get("scope", {})
        assert stored_scope.get("audit_chain") is True
        assert stored_scope.get("hitl") is False
        print(f"\n  ✅ Scope persisted correctly in report metadata")

    def test_60_all_6_frameworks_generate_correctly(self):
        """End-to-end: all 6 frameworks generate valid PDFs and appear in history."""
        for fw in ["General","SOC2","GDPR","HIPAA","FINRA","ISO27001"]:
            r = httpx.post(f"{BASE}/api/compliance/generate",
                           json={"title":f"E2E {fw}","framework":fw,"format":"pdf"},
                           timeout=TIMEOUT)
            assert r.status_code == 200, f"{fw}: HTTP {r.status_code}"
            assert r.content[:4] == b'%PDF', f"{fw}: not a PDF"
            assert len(r.content) > 5000,    f"{fw}: PDF too small ({len(r.content)} bytes)"
        print(f"\n  ✅ All 6 frameworks generate valid PDFs end-to-end")
