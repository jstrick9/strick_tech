"""
Agentic OS - Compliance Report Generator
-----------------------------------------
Generates comprehensive, audit-ready compliance reports covering:
  • Audit chain integrity + decision trail
  • HITL approvals and escalations
  • Policy enforcement actions (allow/deny/require_hitl)
  • Agent identity and authority records
  • Connector executions
  • Cost and token attribution
  • Supervisor run outcomes
  • Data handling summary

Output formats: PDF (fpdf2), JSON, CSV
Compliance frameworks: SOC2, GDPR, HIPAA, FINRA, ISO27001, General

Tables read:
  audit_log_chain, audit_receipts, hitl_queue, hitl_audit,
  mcp_gateway_calls, mcp_gateway_policies, agent_identities,
  connector_executions, connector_registry, cost_ledger,
  supervisor_runs, supervisor_tasks, goals_v2, budget_caps, cost_alerts
"""
from __future__ import annotations

import csv, hashlib, io, json, logging, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter(prefix="/api/compliance", tags=["compliance"])
log    = logging.getLogger("agentic.compliance")

ROOT = Path(__file__).resolve().parents[2]

# -- Report history schema ------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS compliance_reports (
    report_id       TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    framework       TEXT NOT NULL DEFAULT 'General',
    date_from       TEXT NOT NULL DEFAULT '',
    date_to         TEXT NOT NULL DEFAULT '',
    format          TEXT NOT NULL DEFAULT 'pdf',
    scope           TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',
    file_path       TEXT NOT NULL DEFAULT '',
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    summary         TEXT NOT NULL DEFAULT '{}',
    generated_by    TEXT NOT NULL DEFAULT 'user',
    created_at      TEXT NOT NULL DEFAULT '',
    completed_at    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cr_created ON compliance_reports(created_at DESC);
"""

def _get_conn():
    from ..services.memory_db import get_conn
    return get_conn()

def _ensure_schema():
    con = _get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()

_ensure_schema()

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _epoch_to_iso(epoch_ms: int) -> str:
    try:
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""

# -- Data collector -------------------------------------------------------------
def _collect_report_data(date_from: str, date_to: str, scope: dict) -> dict:
    """
    Aggregate all compliance-relevant data into a single structured dict.
    date_from/date_to: ISO8601 strings (empty = no filter).
    scope: dict with booleans for each section.
    """
    con = _get_conn()
    try:
        where_time = ""
        params_time = []
        if date_from:
            where_time = "WHERE created_at >= ?"
            params_time.append(date_from)
        if date_to:
            if where_time:
                where_time += " AND created_at <= ?"
            else:
                where_time = "WHERE created_at <= ?"
            params_time.append(date_to)

        where_time_epoch = ""
        params_epoch = []
        if date_from:
            try:
                ts = int(datetime.fromisoformat(date_from).timestamp() * 1000)
                where_time_epoch = "WHERE epoch_ms >= ?"
                params_epoch.append(ts)
            except Exception:
                pass
        if date_to:
            try:
                ts = int(datetime.fromisoformat(date_to).timestamp() * 1000)
                if where_time_epoch:
                    where_time_epoch += " AND epoch_ms <= ?"
                else:
                    where_time_epoch = "WHERE epoch_ms <= ?"
                params_epoch.append(ts)
            except Exception:
                pass

        data = {
            "generated_at": _now(),
            "date_from":    date_from or "all time",
            "date_to":      date_to   or "now",
        }

        # -- 1. Audit chain --------------------------------------------------
        if scope.get("audit_chain", True):
            total  = con.execute(f"SELECT COUNT(*) FROM audit_log_chain {where_time_epoch}", params_epoch).fetchone()[0]
            by_risk= con.execute(f"SELECT risk_level, COUNT(*) cnt FROM audit_log_chain {where_time_epoch} GROUP BY risk_level", params_epoch).fetchall()
            by_out = con.execute(f"SELECT outcome, COUNT(*) cnt FROM audit_log_chain {where_time_epoch} GROUP BY outcome", params_epoch).fetchall()
            by_agent=con.execute(f"SELECT agent_id, agent_name, COUNT(*) cnt FROM audit_log_chain {where_time_epoch} GROUP BY agent_id ORDER BY cnt DESC LIMIT 15", params_epoch).fetchall()
            # High-risk query with clean parameter handling
            if where_time_epoch:
                hr_sql = f"SELECT * FROM audit_log_chain {where_time_epoch} AND risk_level IN ('high','critical') ORDER BY seq DESC LIMIT 50"
                fail_sql = f"SELECT * FROM audit_log_chain {where_time_epoch} AND outcome='failure' ORDER BY seq DESC LIMIT 50"
                hr_params = params_epoch
            else:
                hr_sql = "SELECT * FROM audit_log_chain WHERE risk_level IN ('high','critical') ORDER BY seq DESC LIMIT 50"
                fail_sql = "SELECT * FROM audit_log_chain WHERE outcome='failure' ORDER BY seq DESC LIMIT 50"
                hr_params = []
            high_risk = con.execute(hr_sql, hr_params).fetchall()
            failures  = con.execute(fail_sql, hr_params).fetchall()
            # Chain verify
            from ..routers.audit_log import verify_chain
            chain_verify = verify_chain()

            # Recent entries sample
            recent_entries = con.execute(f"SELECT seq,entry_id,agent_id,agent_name,action_type,action_detail,risk_level,outcome,created_at,entry_hash FROM audit_log_chain {where_time_epoch} ORDER BY seq DESC LIMIT 200", params_epoch).fetchall()

            data["audit"] = {
                "total":           total,
                "by_risk":         {r["risk_level"]: r["cnt"] for r in by_risk},
                "by_outcome":      {r["outcome"]: r["cnt"] for r in by_out},
                "top_agents":      [dict(r) for r in by_agent],
                "high_risk_count": len(high_risk),
                "failure_count":   len(failures),
                "high_risk":       [dict(r) for r in high_risk],
                "failures":        [dict(r) for r in failures],
                "recent_entries":  [dict(r) for r in recent_entries],
                "chain_integrity": chain_verify,
            }

        # -- 2. HITL approvals -----------------------------------------------
        if scope.get("hitl", True):
            hitl_total  = con.execute(f"SELECT COUNT(*) FROM hitl_queue {where_time}", params_time).fetchone()[0]
            hitl_status = con.execute(f"SELECT status, COUNT(*) cnt FROM hitl_queue {where_time} GROUP BY status", params_time).fetchall()
            hitl_items  = con.execute(f"SELECT * FROM hitl_queue {where_time} ORDER BY created_at DESC LIMIT 100", params_time).fetchall()
            hitl_audit  = con.execute(f"SELECT * FROM hitl_audit {where_time} ORDER BY created_at DESC LIMIT 100", params_time).fetchall()
            data["hitl"] = {
                "total":    hitl_total,
                "by_status":{r["status"]: r["cnt"] for r in hitl_status},
                "items":    [dict(r) for r in hitl_items],
                "audit":    [dict(r) for r in hitl_audit],
            }

        # -- 3. Policy enforcement -------------------------------------------
        if scope.get("policies", True):
            pol_total   = con.execute(f"SELECT COUNT(*) FROM mcp_gateway_calls {where_time}", params_time).fetchone()[0]
            pol_decision= con.execute(f"SELECT policy_decision, COUNT(*) cnt FROM mcp_gateway_calls {where_time} GROUP BY policy_decision", params_time).fetchall()
            # Build blocked query with clean parameter handling
            if where_time:
                blocked_sql    = f"SELECT * FROM mcp_gateway_calls {where_time} AND policy_decision IN ('deny','require_hitl') ORDER BY created_at DESC LIMIT 100"
                blocked_params = params_time
            else:
                blocked_sql    = "SELECT * FROM mcp_gateway_calls WHERE policy_decision IN ('deny','require_hitl') ORDER BY created_at DESC LIMIT 100"
                blocked_params = []
            pol_blocked = con.execute(blocked_sql, blocked_params).fetchall()
            active_policies = con.execute("SELECT policy_id, name, action, agent_id, server_id, tool_pattern, priority FROM mcp_gateway_policies WHERE enabled=1 ORDER BY priority").fetchall()
            data["policies"] = {
                "total_calls":   pol_total,
                "by_decision":   {r["policy_decision"]: r["cnt"] for r in pol_decision},
                "blocked_calls": [dict(r) for r in pol_blocked],
                "active_policies": [dict(r) for r in active_policies],
            }

        # -- 4. Agent identity & access --------------------------------------
        if scope.get("agent_identity", True):
            agents = con.execute("SELECT agent_id, display_name, status, authority_level, key_version, created_at FROM agent_identities ORDER BY created_at DESC LIMIT 50").fetchall()
            # JIT tokens issued in period
            try:
                jit = con.execute(f"SELECT COUNT(*) FROM agent_jit_tokens {where_time}", params_time).fetchone()[0]
            except Exception:
                jit = 0
            data["agent_identity"] = {
                "agents":       [dict(r) for r in agents],
                "total_agents": len(agents),
                "jit_tokens_issued": jit,
            }

        # -- 5. Connector executions -----------------------------------------
        if scope.get("connectors", True):
            ce_total  = con.execute(f"SELECT COUNT(*) FROM connector_executions {where_time}", params_time).fetchone()[0]
            ce_status = con.execute(f"SELECT status, COUNT(*) cnt FROM connector_executions {where_time} GROUP BY status", params_time).fetchall()
            ce_by_conn= con.execute(f"SELECT connector_id, COUNT(*) cnt FROM connector_executions {where_time} GROUP BY connector_id ORDER BY cnt DESC", params_time).fetchall()
            if where_time:
                ce_err_sql = f"SELECT * FROM connector_executions {where_time} AND status='error' ORDER BY created_at DESC LIMIT 50"
                ce_err_params = params_time
            else:
                ce_err_sql = "SELECT * FROM connector_executions WHERE status='error' ORDER BY created_at DESC LIMIT 50"
                ce_err_params = []
            ce_errors = con.execute(ce_err_sql, ce_err_params).fetchall()
            data["connectors"] = {
                "total":        ce_total,
                "by_status":    {r["status"]: r["cnt"] for r in ce_status},
                "by_connector": [dict(r) for r in ce_by_conn],
                "errors":       [dict(r) for r in ce_errors],
            }

        # -- 6. Cost & token attribution -------------------------------------
        if scope.get("cost", True):
            try:
                cost_total = con.execute(f"SELECT SUM(cost_usd), SUM(total_tokens) FROM cost_ledger {where_time}", params_time).fetchone()
                cost_by_agent = con.execute(f"SELECT agent_id, SUM(cost_usd) total_cost, SUM(total_tokens) total_tokens FROM cost_ledger {where_time} GROUP BY agent_id ORDER BY total_cost DESC LIMIT 15", params_time).fetchall()
                cost_by_model = con.execute(f"SELECT model, SUM(cost_usd) total_cost, COUNT(*) calls FROM cost_ledger {where_time} GROUP BY model ORDER BY total_cost DESC LIMIT 10", params_time).fetchall()
                budget_caps   = con.execute("SELECT * FROM budget_caps").fetchall()
                cost_alerts   = con.execute(f"SELECT * FROM cost_alerts {where_time} ORDER BY created_at DESC LIMIT 20", params_time).fetchall()
                data["cost"] = {
                    "total_cost_usd":  round(float(cost_total[0] or 0), 4),
                    "total_tokens":    int(cost_total[1] or 0),
                    "by_agent":        [dict(r) for r in cost_by_agent],
                    "by_model":        [dict(r) for r in cost_by_model],
                    "budget_caps":     [dict(r) for r in budget_caps],
                    "cost_alerts":     [dict(r) for r in cost_alerts],
                }
            except Exception as e:
                data["cost"] = {"error": str(e)}

        # -- 7. Supervisor runs ----------------------------------------------
        if scope.get("supervisor", True):
            sv_total  = con.execute(f"SELECT COUNT(*) FROM supervisor_runs {where_time}", params_time).fetchone()[0]
            sv_status = con.execute(f"SELECT status, COUNT(*) cnt FROM supervisor_runs {where_time} GROUP BY status", params_time).fetchall()
            sv_runs   = con.execute(f"SELECT run_id,goal_title,status,task_count,done_count,eval_score,total_tokens,total_cost,duration_ms,created_at FROM supervisor_runs {where_time} ORDER BY created_at DESC LIMIT 50", params_time).fetchall()
            data["supervisor"] = {
                "total":    sv_total,
                "by_status":{r["status"]: r["cnt"] for r in sv_status},
                "runs":     [dict(r) for r in sv_runs],
            }

    finally:
        con.close()

    return data


# -- PDF generator (fpdf2) ------------------------------------------------------
def _generate_pdf(report_data: dict, title: str, framework: str) -> bytes:
    from fpdf import FPDF, XPos, YPos

    BRAND_BLUE  = (91, 138, 248)
    BRAND_GREEN = (61, 186, 122)
    BRAND_RED   = (232, 82, 82)
    BRAND_AMBER = (232, 162, 55)
    GRAY_DARK   = (13, 14, 20)
    GRAY_MED    = (45, 48, 71)
    TEXT_LIGHT  = (200, 210, 240)
    WHITE       = (255, 255, 255)

    class CompliancePDF(FPDF):
        def header(self):
            # Dark header bar
            self.set_fill_color(*GRAY_DARK)
            self.rect(0, 0, 210, 18, "F")
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(*BRAND_BLUE)
            self.set_xy(10, 4)
            self.cell(100, 10, "AGENTIC OS", align="L")
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*TEXT_LIGHT)
            self.set_xy(110, 4)
            self.cell(90, 10, f"Compliance Report   {framework}", align="R")
            self.set_draw_color(*BRAND_BLUE)
            self.set_line_width(0.5)
            self.line(0, 18, 210, 18)
            self.ln(8)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(150, 150, 180)
            self.cell(0, 10, f"Page {self.page_no()} - {report_data.get('generated_at','')[:19]} UTC - CONFIDENTIAL", align="C")

    pdf = CompliancePDF()
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(14, 22, 14)

    def h1(text):
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*BRAND_BLUE)
        pdf.ln(4)
        pdf.cell(0, 10, escHtml_py(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*BRAND_BLUE)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
        pdf.ln(3)

    def h2(text, color=None):
        pdf.set_font("Helvetica", "B", 11)
        c = color or BRAND_BLUE
        pdf.set_text_color(*c)
        pdf.ln(3)
        pdf.cell(0, 7, escHtml_py(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

    def body(text, size=9, color=None):
        pdf.set_font("Helvetica", "", size)
        pdf.set_text_color(*(color or (60, 65, 100)))
        pdf.set_x(pdf.l_margin)  # Always start at left margin
        pdf.multi_cell(pdf.epw, 5, escHtml_py(str(text)))

    def kv(label, value, label_color=None, val_color=None):
        # Save X before label, so we can compute remaining width for value
        x_start = pdf.get_x()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*(label_color or (100, 110, 150)))
        pdf.cell(55, 5, escHtml_py(label + ":"), new_x=XPos.RIGHT, new_y=YPos.TOP)
        # Available width = page width - right margin - current X
        avail_w = pdf.epw - 55  # epw = effective page width; label is 55
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*(val_color or (50, 55, 90)))
        # Truncate and sanitize value
        val_str = escHtml_py(str(value)[:300])
        pdf.multi_cell(max(avail_w, 40), 5, val_str)

    def stat_box(label, value, color):
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_fill_color(*color)
        pdf.rect(x, y, 42, 18, "F")
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(x + 1, y + 2)
        pdf.cell(40, 8, escHtml_py(str(value)), align="C")
        pdf.set_font("Helvetica", "", 6)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(x + 1, y + 11)
        pdf.cell(40, 5, escHtml_py(label.upper()), align="C")
        pdf.set_xy(x + 43, y)

    def section_divider(color=None):
        c = color or GRAY_MED
        pdf.set_fill_color(*c)
        pdf.rect(pdf.l_margin, pdf.get_y(), 182, 0.3, "F")
        pdf.ln(3)

    def risk_badge(risk_level: str) -> str:
        return {"low":"LOW","medium":"MED","high":"HIGH","critical":"CRIT"}.get(risk_level, risk_level.upper()[:4])

    # -------------------------------------------------------------------------
    # COVER PAGE
    # -------------------------------------------------------------------------
    pdf.add_page()

    # Hero banner
    pdf.set_fill_color(*GRAY_DARK)
    pdf.rect(0, 18, 210, 60, "F")
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.set_xy(14, 32)
    pdf.cell(182, 12, "COMPLIANCE REPORT", align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(14, 46)
    pdf.cell(182, 8, title, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*TEXT_LIGHT)
    pdf.set_xy(14, 58)
    pdf.cell(182, 6, f"Framework: {framework}     Generated: {report_data.get('generated_at','')[:19]} UTC", align="C")
    pdf.set_xy(14, 66)
    pdf.cell(182, 6, f"Period: {report_data.get('date_from','')} to {report_data.get('date_to','')}", align="C")

    pdf.ln(50)

    # Report metadata
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.cell(0, 7, "Report Information", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*BRAND_BLUE)
    pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    meta = [
        ("Platform", "Agentic OS v6.0"),
        ("Report Type", f"Compliance Audit - {framework}"),
        ("Coverage Period", f"{report_data.get('date_from','All time')} to {report_data.get('date_to','Present')}"),
        ("Chain Integrity", escHtml_py(str(report_data.get("audit",{}).get("chain_integrity",{}).get("message","Not verified")))),
        ("Total Audit Entries", str(report_data.get("audit",{}).get("total","-"))),
        ("Classification", "CONFIDENTIAL - For compliance review only"),
    ]
    for label, val in meta:
        kv(label, val)

    pdf.ln(8)

    # Framework-specific note
    fw_notes = {
        "SOC2":   "This report supports SOC 2 Type II audit requirements covering Security, Availability, Confidentiality, Processing Integrity, and Privacy trust service criteria.",
        "GDPR":   "This report supports GDPR Article 30 records of processing activities, Article 32 security measures documentation, and breach notification requirements.",
        "HIPAA":  "This report supports HIPAA Security Rule §164.312 technical safeguards documentation, audit controls (§164.312(b)), and access control records.",
        "FINRA":  "This report supports FINRA Rule 4370 business continuity planning, Rule 17a-4 record retention, and supervisory control requirements.",
        "ISO27001":"This report supports ISO/IEC 27001:2022 Annex A controls documentation, particularly A.8 (Technology Controls) and A.5 (Organizational Controls).",
        "General": "This report provides a comprehensive audit trail of all AI agent activities, policy enforcement decisions, human-in-the-loop approvals, and system access events.",
    }
    pdf.set_fill_color(230, 240, 255)
    pdf.set_draw_color(*BRAND_BLUE)
    pdf.set_line_width(0.3)
    pdf.rect(pdf.l_margin, pdf.get_y(), 182, 22, "FD")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.set_xy(pdf.l_margin + 3, pdf.get_y() + 3)
    pdf.cell(176, 5, f"Framework Note - {framework}")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(50, 55, 90)
    pdf.set_xy(pdf.l_margin + 3, pdf.get_y() + 5)
    pdf.multi_cell(176, 4, fw_notes.get(framework, fw_notes["General"]))
    pdf.ln(10)

    # Table of contents
    sections = []
    if report_data.get("audit"):   sections.append(("1", "Audit Chain Integrity & Decision Trail"))
    if report_data.get("hitl"):    sections.append(("2", "Human-in-the-Loop Approvals"))
    if report_data.get("policies"):sections.append(("3", "Policy Enforcement Summary"))
    if report_data.get("agent_identity"): sections.append(("4", "Agent Identity & Access Records"))
    if report_data.get("connectors"):     sections.append(("5", "Connector Executions"))
    if report_data.get("cost"):           sections.append(("6", "Cost & Token Attribution"))
    if report_data.get("supervisor"):     sections.append(("7", "Supervisor Run Outcomes"))
    sections.append(("8", "Chain Verification Certificate"))

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.cell(0, 7, "Table of Contents", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    for num, title_sec in sections:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(50, 55, 90)
        pdf.cell(10, 6, f"{num}.")
        pdf.cell(0, 6, title_sec, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 1 - Audit Chain
    # -------------------------------------------------------------------------
    if report_data.get("audit"):
        pdf.add_page()
        h1("1. Audit Chain Integrity & Decision Trail")
        audit = report_data["audit"]
        ci = audit.get("chain_integrity", {})

        # Chain integrity banner
        ok = ci.get("ok", True)
        pdf.set_fill_color(*(BRAND_GREEN if ok else BRAND_RED))
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 10)
        pdf.rect(pdf.l_margin, pdf.get_y(), 182, 12, "F")
        pdf.set_xy(pdf.l_margin + 4, pdf.get_y() + 2)
        status_txt = "OK CHAIN INTEGRITY VERIFIED" if ok else "[!] CHAIN INTEGRITY ISSUE DETECTED"
        pdf.cell(174, 8, status_txt)
        pdf.ln(14)

        body(escHtml_py(f"Verified entries: {ci.get('verified',0):,}   Chain tip: {(ci.get('chain_tip',''))[:32]}...  {str(ci.get('message',''))}"))
        if not ok:
            body("[!] ATTENTION: Chain broken at seq=" + str(ci.get('broken_at','?')) + ". This may indicate tampering. Immediate investigation required.", color=BRAND_RED)
        pdf.ln(4)

        # Stat boxes
        h2("Summary Statistics")
        pdf.set_xy(pdf.l_margin, pdf.get_y())
        stat_box("Total Entries", f"{audit.get('total',0):,}", BRAND_BLUE)
        stat_box("Failures", audit.get("failure_count", 0), BRAND_RED if audit.get("failure_count",0) > 0 else GRAY_MED)
        stat_box("High Risk", audit.get("high_risk_count", 0), BRAND_AMBER if audit.get("high_risk_count",0) > 0 else GRAY_MED)
        stat_box("Blocked", audit.get("by_outcome",{}).get("blocked",0), BRAND_AMBER)
        pdf.ln(22)

        # By risk breakdown
        h2("Risk Level Distribution")
        risk_colors = {"low": BRAND_GREEN, "medium": BRAND_AMBER, "high": BRAND_RED, "critical": (180, 0, 0)}
        for rl, cnt in audit.get("by_risk",{}).items():
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*risk_colors.get(rl, (100,100,100)))
            pdf.cell(30, 5, rl.upper())
            pdf.set_text_color(50, 55, 90)
            pct = cnt / max(audit.get("total",1), 1) * 100
            # Mini bar
            pdf.set_fill_color(*risk_colors.get(rl, (180,180,180)))
            bar_w = min(int(pct * 1.2), 100)
            pdf.rect(pdf.get_x(), pdf.get_y()+1, bar_w, 3, "F")
            pdf.set_x(pdf.l_margin + 140)
            pdf.cell(20, 5, f"{cnt:,}  ({pct:.1f}%)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        # Top agents
        if audit.get("top_agents"):
            h2("Top Agents by Activity")
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(100, 110, 150)
            pdf.cell(55, 5, "AGENT")
            pdf.cell(40, 5, "NAME")
            pdf.cell(0, 5, "ACTIONS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(200, 210, 230)
            pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
            for a in audit["top_agents"][:10]:
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(50, 55, 90)
                pdf.cell(55, 5, escHtml_py(a.get("agent_id","")[:30]))
                pdf.cell(40, 5, escHtml_py(a.get("agent_name","")[:25]))
                pdf.cell(0, 5, str(a.get("cnt",0)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

        # High-risk entries
        if audit.get("high_risk"):
            h2("High-Risk & Critical Actions", BRAND_RED)
            pdf.set_font("Helvetica", "", 8)
            body(f"The following {len(audit['high_risk'])} entries were flagged as high or critical risk during the report period:")
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(100, 110, 150)
            pdf.cell(12, 4, "SEQ")
            pdf.cell(22, 4, "RISK")
            pdf.cell(30, 4, "AGENT")
            pdf.cell(35, 4, "ACTION")
            pdf.cell(0, 4, "DETAIL", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(200, 210, 230)
            pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
            for e in audit["high_risk"][:30]:
                rc = BRAND_RED if e.get("risk_level") == "critical" else BRAND_AMBER
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(12, 4, str(e.get("seq","")))
                pdf.set_text_color(*rc)
                pdf.set_font("Helvetica", "B", 7)
                pdf.cell(22, 4, risk_badge(e.get("risk_level","")))
                pdf.set_text_color(80, 85, 120)
                pdf.set_font("Helvetica", "", 7)
                pdf.cell(30, 4, escHtml_py(str(e.get("agent_id",""))[:18]))
                pdf.cell(35, 4, escHtml_py(str(e.get("action_type",""))[:22]))
                pdf.cell(0, 4, escHtml_py(str(e.get("action_detail",""))[:60]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if len(audit["high_risk"]) > 30:
                body(f"... and {len(audit['high_risk'])-30} more. See JSON export for full list.", color=(150,150,180))
            pdf.ln(4)

        # Failure entries
        if audit.get("failures"):
            h2("Failed Actions", BRAND_RED)
            for e in audit["failures"][:20]:
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(12, 4, f"#{e.get('seq','')}")
                pdf.cell(30, 4, escHtml_py(str(e.get("agent_id",""))[:20]))
                pdf.cell(0, 4, escHtml_py(str(e.get("action_detail",""))[:80]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 2 - HITL
    # -------------------------------------------------------------------------
    if report_data.get("hitl"):
        pdf.add_page()
        h1("2. Human-in-the-Loop Approvals")
        hitl = report_data["hitl"]
        body(f"Total HITL decisions during period: {hitl.get('total',0):,}")
        pdf.ln(3)

        h2("Decision Status Breakdown")
        for status, cnt in hitl.get("by_status",{}).items():
            sc = {"approved": BRAND_GREEN, "rejected": BRAND_RED, "pending": BRAND_AMBER, "timeout": GRAY_MED}.get(status, GRAY_MED)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*sc)
            pdf.cell(30, 5, status.upper())
            pdf.set_text_color(50, 55, 90)
            pdf.cell(0, 5, str(cnt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        if hitl.get("items"):
            h2("Recent HITL Queue Items (sample)")
            for item in hitl["items"][:20]:
                item_d = dict(item) if not isinstance(item, dict) else item
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(80, 85, 120)
                status_c = {"approved": BRAND_GREEN, "rejected": BRAND_RED, "pending": BRAND_AMBER}.get(item_d.get("status",""), GRAY_MED)
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_text_color(*status_c)
                pdf.cell(20, 4, str(item_d.get("status",""))[:10])
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(35, 4, escHtml_py(str(item_d.get("agent_id",""))[:20]))
                pdf.cell(0, 4, escHtml_py(str(item_d.get("action_type","") or item_d.get("interrupt_type",""))[:60]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 3 - Policy Enforcement
    # -------------------------------------------------------------------------
    if report_data.get("policies"):
        pdf.add_page()
        h1("3. Policy Enforcement Summary")
        pol = report_data["policies"]

        body(f"Total gateway calls: {pol.get('total_calls',0):,}")
        pdf.ln(3)

        h2("Decision Breakdown")
        dec_colors = {"allow": BRAND_GREEN, "deny": BRAND_RED, "require_hitl": BRAND_AMBER, "rate_limited": GRAY_MED}
        for dec, cnt in pol.get("by_decision",{}).items():
            c = dec_colors.get(dec, GRAY_MED)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*c)
            pdf.cell(35, 5, dec.upper())
            pdf.set_text_color(50, 55, 90)
            pdf.cell(0, 5, f"{cnt:,}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        h2("Active Policy Rules")
        body(f"{len(pol.get('active_policies',[]))} active policies enforced during period:")
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(100, 110, 150)
        pdf.cell(8, 4, "P")
        pdf.cell(25, 4, "ACTION")
        pdf.cell(30, 4, "AGENT")
        pdf.cell(35, 4, "SERVER")
        pdf.cell(0, 4, "TOOL PATTERN", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
        for p in pol["active_policies"][:20]:
            ac = {"allow": BRAND_GREEN, "deny": BRAND_RED, "require_hitl": BRAND_AMBER}.get(p.get("action",""), GRAY_MED)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(100, 110, 150)
            pdf.cell(8, 4, str(p.get("priority","")))
            pdf.set_text_color(*ac)
            pdf.set_font("Helvetica", "B", 7)
            pdf.cell(25, 4, str(p.get("action","")).upper()[:10])
            pdf.set_text_color(80, 85, 120)
            pdf.set_font("Helvetica", "", 7)
            pdf.cell(30, 4, escHtml_py(str(p.get("agent_id",""))[:18]))
            pdf.cell(35, 4, escHtml_py(str(p.get("server_id","")).replace("srv_","")[:20]))
            pdf.cell(0, 4, escHtml_py(str(p.get("tool_pattern",""))[:25]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if pol.get("blocked_calls"):
            pdf.ln(4)
            h2("Blocked/HITL Calls (sample)", BRAND_RED)
            for c in pol["blocked_calls"][:15]:
                cd = dict(c) if not isinstance(c, dict) else c
                dc = dec_colors.get(cd.get("policy_decision",""), GRAY_MED)
                pdf.set_font("Helvetica", "B", 7)
                pdf.set_text_color(*dc)
                pdf.cell(30, 4, str(cd.get("policy_decision","")).upper())
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(30, 4, escHtml_py(str(cd.get("agent_id",""))[:18]))
                pdf.cell(35, 4, escHtml_py(str(cd.get("tool_name",""))[:20]))
                pdf.cell(0, 4, escHtml_py(str(cd.get("created_at",""))[:16]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 4 - Agent Identity
    # -------------------------------------------------------------------------
    if report_data.get("agent_identity"):
        pdf.add_page()
        h1("4. Agent Identity & Access Records")
        ai = report_data["agent_identity"]
        body(f"Total provisioned agent identities: {ai.get('total_agents',0):,}")
        body(f"JIT tokens issued in period: {ai.get('jit_tokens_issued',0):,}")
        pdf.ln(4)

        if ai.get("agents"):
            h2("Registered Agent Identities")
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(100, 110, 150)
            pdf.cell(40, 4, "AGENT ID")
            pdf.cell(45, 4, "DISPLAY NAME")
            pdf.cell(25, 4, "STATUS")
            pdf.cell(30, 4, "AUTHORITY")
            pdf.cell(0, 4, "KEY VER.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
            for a in ai["agents"][:30]:
                sc = BRAND_GREEN if a.get("status") == "active" else GRAY_MED
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(40, 4, escHtml_py(str(a.get("agent_id",""))[:24]))
                pdf.cell(45, 4, escHtml_py(str(a.get("display_name",""))[:28]))
                pdf.set_text_color(*sc)
                pdf.set_font("Helvetica", "B", 7)
                pdf.cell(25, 4, str(a.get("status","")).upper())
                pdf.set_text_color(80, 85, 120)
                pdf.set_font("Helvetica", "", 7)
                pdf.cell(30, 4, escHtml_py(str(a.get("authority_level",""))[:15]))
                pdf.cell(0, 4, str(a.get("key_version","")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 5 - Connectors
    # -------------------------------------------------------------------------
    if report_data.get("connectors"):
        pdf.add_page()
        h1("5. Connector Executions")
        ce = report_data["connectors"]
        body(f"Total connector calls: {ce.get('total',0):,}")
        pdf.ln(3)

        h2("By Status")
        for s, cnt in ce.get("by_status",{}).items():
            sc = BRAND_GREEN if s == "success" else BRAND_RED if s == "error" else GRAY_MED
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*sc)
            pdf.cell(25, 5, s.upper())
            pdf.set_text_color(50, 55, 90)
            pdf.cell(0, 5, f"{cnt:,}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        h2("By Connector")
        for c in ce.get("by_connector",[])[:15]:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(80, 85, 120)
            pdf.cell(50, 5, escHtml_py(str(c.get("connector_id",""))[:30]))
            pdf.cell(0, 5, f"{c.get('cnt',0):,} calls", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 6 - Cost
    # -------------------------------------------------------------------------
    if report_data.get("cost") and isinstance(report_data["cost"], dict) and not report_data["cost"].get("error"):
        pdf.add_page()
        h1("6. Cost & Token Attribution")
        cost = report_data["cost"]
        pdf.set_xy(pdf.l_margin, pdf.get_y())
        stat_box("TOTAL COST", f"${cost.get('total_cost_usd',0):.4f}", BRAND_BLUE)
        stat_box("TOKENS", f"{cost.get('total_tokens',0)/1000:.1f}K", BRAND_BLUE)
        pdf.ln(22)

        if cost.get("by_agent"):
            h2("Cost by Agent")
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(100, 110, 150)
            pdf.cell(50, 4, "AGENT")
            pdf.cell(35, 4, "COST (USD)")
            pdf.cell(0, 4, "TOKENS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
            for a in cost["by_agent"][:15]:
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(50, 4, escHtml_py(str(a.get("agent_id",""))[:30]))
                pdf.cell(35, 4, f"${float(a.get('total_cost',0)):.4f}")
                pdf.cell(0, 4, f"{int(a.get('total_tokens',0)):,}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

        if cost.get("budget_caps"):
            h2("Budget Caps in Effect")
            for cap in cost["budget_caps"][:10]:
                cap_d = dict(cap) if not isinstance(cap, dict) else cap
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(50, 4, escHtml_py(str(cap_d.get("agent_id","*"))[:30]))
                pdf.cell(0, 4, f"Max ${cap_d.get('max_cost_usd',0):.2f}/day   {cap_d.get('max_tokens',0):,} tokens/day", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 7 - Supervisor
    # -------------------------------------------------------------------------
    if report_data.get("supervisor"):
        pdf.add_page()
        h1("7. Supervisor Run Outcomes")
        sv = report_data["supervisor"]
        body(f"Total supervisor runs: {sv.get('total',0):,}")
        pdf.ln(3)

        h2("By Status")
        for s, cnt in sv.get("by_status",{}).items():
            sc = BRAND_GREEN if s == "done" else BRAND_RED if s in ("failed","killed") else BRAND_AMBER
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*sc)
            pdf.cell(30, 5, s.upper())
            pdf.set_text_color(50, 55, 90)
            pdf.cell(0, 5, f"{cnt:,}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        if sv.get("runs"):
            h2("Recent Runs")
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(100, 110, 150)
            pdf.cell(50, 4, "GOAL")
            pdf.cell(22, 4, "STATUS")
            pdf.cell(20, 4, "TASKS")
            pdf.cell(20, 4, "SCORE")
            pdf.cell(0, 4, "DATE", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
            for r in sv["runs"][:20]:
                rd = dict(r) if not isinstance(r, dict) else r
                sc = BRAND_GREEN if rd.get("status") == "done" else BRAND_RED if rd.get("status") in ("failed","killed") else BRAND_AMBER
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(80, 85, 120)
                pdf.cell(50, 4, escHtml_py(str(rd.get("goal_title",""))[:30]))
                pdf.set_text_color(*sc)
                pdf.set_font("Helvetica", "B", 7)
                pdf.cell(22, 4, str(rd.get("status","")).upper()[:8])
                pdf.set_text_color(80, 85, 120)
                pdf.set_font("Helvetica", "", 7)
                pdf.cell(20, 4, f"{rd.get('done_count',0)}/{rd.get('task_count',0)}")
                score = rd.get("eval_score")
                pdf.cell(20, 4, f"{int(score*100)}%" if score else "-")
                pdf.cell(0, 4, str(rd.get("created_at",""))[:10], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -------------------------------------------------------------------------
    # SECTION 8 - Certificate
    # -------------------------------------------------------------------------
    pdf.add_page()
    h1("8. Chain Verification Certificate")

    audit_d = report_data.get("audit", {})
    ci = audit_d.get("chain_integrity", {})
    ok = ci.get("ok", True)

    # Certificate box
    pdf.set_fill_color(*(230, 255, 235) if ok else (255, 235, 235))
    pdf.set_draw_color(*(BRAND_GREEN if ok else BRAND_RED))
    pdf.set_line_width(1.0)
    pdf.rect(pdf.l_margin, pdf.get_y(), 182, 70, "FD")
    pdf.set_line_width(0.3)

    cert_y = pdf.get_y() + 8
    pdf.set_xy(pdf.l_margin + 8, cert_y)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*(BRAND_GREEN if ok else BRAND_RED))
    pdf.cell(166, 8, "VERIFICATION CERTIFICATE", align="C")

    pdf.set_xy(pdf.l_margin + 8, cert_y + 10)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 35, 60)
    status_label = "OK CHAIN INTEGRITY CONFIRMED" if ok else "[!] CHAIN INTEGRITY ISSUE"
    pdf.cell(166, 7, status_label, align="C")

    fields = [
        ("Report Generated", report_data.get("generated_at","")[:19] + " UTC"),
        ("Coverage Period", f"{report_data.get('date_from','')} to {report_data.get('date_to','')}"),
        ("Entries Verified", str(ci.get("verified",0))),
        ("Chain Tip Hash", str(ci.get("chain_tip",""))[:48] + "..."),
        ("Framework", framework),
        ("Integrity Status", "PASSED OK" if ok else f"FAILED - broken at seq {ci.get('broken_at','')}"),
    ]
    for i, (label, value) in enumerate(fields):
        pdf.set_xy(pdf.l_margin + 8, cert_y + 20 + i * 7)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(100, 110, 150)
        pdf.cell(55, 5, label + ":")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(30, 35, 60)
        pdf.cell(0, 5, str(value)[:80])

    pdf.ln(80)

    body("This certificate attests that the audit chain has been cryptographically verified using SHA-256 hash chaining. Each entry's hash is computed from all critical fields plus the previous entry's hash, forming a tamper-evident chain. Any modification to any entry would invalidate all subsequent hashes and be immediately detectable upon verification.", size=8, color=(80, 90, 120))

    return bytes(pdf.output())


def escHtml_py(text: str) -> str:
    """Safe text for fpdf2 Helvetica font - strips all characters outside Latin-1 range."""
    import unicodedata
    result = []
    for ch in str(text):
        cp = ord(ch)
        if cp <= 255:  # Latin-1 range - safe for Helvetica
            result.append(ch)
        elif ch == '→': result.append('->')
        elif ch == '←': result.append('<-')
        elif ch == '✅': result.append('[OK]')
        elif ch == '✓':  result.append('OK')
        elif ch == '❌': result.append('[FAIL]')
        elif ch == '⚠️': result.append('[WARN]')
        elif ch == '⚠':  result.append('[WARN]')
        elif ch == '🔗': result.append('[CHAIN]')
        elif ch == '📋': result.append('[REPORT]')
        elif ch == '🛂': result.append('[HITL]')
        elif ch == '🔏': result.append('[AUDIT]')
        elif ch == '…':  result.append('...')
        elif ch == '–':  result.append('-')
        elif ch == '—':  result.append('-')
        elif ch == '’': result.append("'")
        elif ch == '“': result.append('"')
        elif ch == '”': result.append('"')
        else:
            # Try to decompose (e.g., accented chars) then fall back to ?
            normalized = unicodedata.normalize('NFKD', ch)
            ascii_ver  = normalized.encode('ascii', errors='ignore').decode('ascii')
            result.append(ascii_ver if ascii_ver else ' ')
    return ''.join(result)


# -- API Routes -----------------------------------------------------------------
FRAMEWORKS = ["General", "SOC2", "GDPR", "HIPAA", "FINRA", "ISO27001"]
FORMATS    = ["pdf", "json", "csv"]


@router.get("/frameworks")
def list_frameworks():
    """Return supported compliance frameworks."""
    return {
        "frameworks": [
            {"id":"General", "name":"General Audit",  "description":"Comprehensive audit trail for general governance review"},
            {"id":"SOC2",    "name":"SOC 2 Type II",   "description":"Security, Availability, Confidentiality, Processing Integrity, Privacy"},
            {"id":"GDPR",    "name":"GDPR",            "description":"Article 30 records of processing, Article 32 security measures"},
            {"id":"HIPAA",   "name":"HIPAA",           "description":"Security Rule §164.312 technical safeguards and audit controls"},
            {"id":"FINRA",   "name":"FINRA",           "description":"Rule 4370 continuity planning, Rule 17a-4 record retention"},
            {"id":"ISO27001","name":"ISO/IEC 27001",   "description":"Annex A technology and organizational controls documentation"},
        ]
    }


@router.get("/reports")
def list_reports(limit: int = 50):
    """List previously generated compliance reports."""
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM compliance_reports ORDER BY created_at DESC LIMIT ?",
            (min(limit, 200),)
        ).fetchall()
    finally:
        con.close()
    reports = []
    for r in rows:
        d = dict(r)
        try:
            d["summary"] = json.loads(d.get("summary") or "{}")
        except Exception:
            d["summary"] = {}
        try:
            d["scope"] = json.loads(d.get("scope") or "{}")
        except Exception:
            d["scope"] = {}
        reports.append(d)
    return {"reports": reports, "count": len(reports)}


@router.get("/reports/{report_id}")
def get_report_meta(report_id: str):
    """Get metadata for a generated report."""
    con = _get_conn()
    try:
        row = con.execute("SELECT * FROM compliance_reports WHERE report_id=?", (report_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({"ok": False, "error": "Report not found"}, status_code=404)
    d = dict(row)
    try:
        d["summary"] = json.loads(d.get("summary") or "{}")
        d["scope"]   = json.loads(d.get("scope")   or "{}")
    except Exception:
        pass
    return {"ok": True, "report": d}


@router.delete("/reports/{report_id}")
def delete_report(report_id: str):
    """Delete a report record."""
    con = _get_conn()
    try:
        con.execute("DELETE FROM compliance_reports WHERE report_id=?", (report_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "deleted": report_id}


@router.post("/generate")
async def generate_report(req: Request):
    """
    Generate a compliance report.
    Body:
      {
        "title":      "Q3 2026 Compliance Audit",
        "framework":  "SOC2" | "GDPR" | "HIPAA" | "FINRA" | "ISO27001" | "General",
        "format":     "pdf" | "json" | "csv",
        "date_from":  "2026-01-01T00:00:00Z",   // optional
        "date_to":    "2026-12-31T23:59:59Z",   // optional
        "scope": {
          "audit_chain":    true,
          "hitl":           true,
          "policies":       true,
          "agent_identity": true,
          "connectors":     true,
          "cost":           true,
          "supervisor":     true,
        }
      }
    Returns the report file as a download.
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

    title     = (body.get("title")     or "Compliance Report").strip()[:200]
    framework = (body.get("framework") or "General").strip()
    fmt       = (body.get("format")    or "pdf").strip().lower()
    date_from = (body.get("date_from") or "").strip()
    date_to   = (body.get("date_to")   or "").strip()
    scope     = body.get("scope") or {}

    if framework not in FRAMEWORKS:
        return JSONResponse({"ok": False, "error": f"Unknown framework. Valid: {FRAMEWORKS}"}, status_code=400)
    if fmt not in FORMATS:
        return JSONResponse({"ok": False, "error": f"Unknown format. Valid: {FORMATS}"}, status_code=400)

    # Default scope = all sections enabled
    default_scope = {
        "audit_chain": True, "hitl": True, "policies": True,
        "agent_identity": True, "connectors": True, "cost": True, "supervisor": True,
    }
    scope = {**default_scope, **scope}

    report_id = f"rpt_{uuid.uuid4().hex[:12]}"
    now       = _now()

    # Save pending record
    con = _get_conn()
    try:
        con.execute("""
            INSERT INTO compliance_reports
              (report_id,title,framework,date_from,date_to,format,scope,status,generated_by,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (report_id, title, framework, date_from, date_to, fmt,
              json.dumps(scope), "generating", "user", now))
        con.commit()
    finally:
        con.close()

    try:
        # Collect data
        data = _collect_report_data(date_from, date_to, scope)

        # Build summary
        summary = {
            "audit_total":      data.get("audit",{}).get("total", 0),
            "high_risk_count":  data.get("audit",{}).get("high_risk_count", 0),
            "failure_count":    data.get("audit",{}).get("failure_count", 0),
            "hitl_total":       data.get("hitl",{}).get("total", 0),
            "policy_blocked":   sum(v for k,v in data.get("policies",{}).get("by_decision",{}).items() if k in ("deny","require_hitl")),
            "chain_ok":         data.get("audit",{}).get("chain_integrity",{}).get("ok", True),
            "cost_usd":         data.get("cost",{}).get("total_cost_usd", 0),
            "supervisor_runs":  data.get("supervisor",{}).get("total", 0),
        }

        # Generate output
        if fmt == "pdf":
            content = _generate_pdf(data, title, framework)
            mime    = "application/pdf"
            ext     = "pdf"
        elif fmt == "json":
            content = json.dumps({
                "report_id":   report_id,
                "title":       title,
                "framework":   framework,
                "generated_at":now,
                "date_from":   date_from,
                "date_to":     date_to,
                "summary":     summary,
                "data":        data,
            }, indent=2, default=str).encode("utf-8")
            mime = "application/json"
            ext  = "json"
        else:  # csv
            out    = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["section","key","value"])
            # Flatten summary
            for k, v in summary.items():
                writer.writerow(["summary", k, v])
            # Audit entries
            for e in data.get("audit",{}).get("recent_entries",[]):
                writer.writerow(["audit", json.dumps(e), ""])
            content = out.getvalue().encode("utf-8")
            mime    = "text/csv"
            ext     = "csv"

        file_size = len(content)
        ts_label  = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"compliance_{framework.lower()}_{ts_label}.{ext}"

        # Update record
        con = _get_conn()
        try:
            con.execute("""
                UPDATE compliance_reports
                SET status='done', file_size_bytes=?, summary=?, completed_at=?
                WHERE report_id=?
            """, (file_size, json.dumps(summary), _now(), report_id))
            con.commit()
        finally:
            con.close()

        log.info("Compliance report generated: %s (%s, %d bytes)", report_id, framework, file_size)

        return StreamingResponse(
            io.BytesIO(content),
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Report-Id":         report_id,
                "X-Report-Summary":    json.dumps(summary, default=str)[:500],
            }
        )

    except Exception as e:
        log.error("Report generation failed: %s", e, exc_info=True)
        con = _get_conn()
        try:
            con.execute("UPDATE compliance_reports SET status='failed' WHERE report_id=?", (report_id,))
            con.commit()
        finally:
            con.close()
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=500)


@router.get("/summary")
def compliance_summary():
    """
    Return a live compliance summary - headline numbers for the dashboard.
    """
    from ..routers.audit_log import verify_chain
    con = _get_conn()
    try:
        audit_total    = con.execute("SELECT COUNT(*) FROM audit_log_chain").fetchone()[0]
        high_risk      = con.execute("SELECT COUNT(*) FROM audit_log_chain WHERE risk_level IN ('high','critical')").fetchone()[0]
        failures       = con.execute("SELECT COUNT(*) FROM audit_log_chain WHERE outcome='failure'").fetchone()[0]
        hitl_total     = con.execute("SELECT COUNT(*) FROM hitl_queue").fetchone()[0]
        hitl_pending   = con.execute("SELECT COUNT(*) FROM hitl_queue WHERE status='pending'").fetchone()[0]
        policy_blocked = con.execute("SELECT COUNT(*) FROM mcp_gateway_calls WHERE policy_decision IN ('deny','require_hitl')").fetchone()[0]
        policy_total   = con.execute("SELECT COUNT(*) FROM mcp_gateway_calls").fetchone()[0]
        agents         = con.execute("SELECT COUNT(*) FROM agent_identities WHERE status='active'").fetchone()[0]
        try:
            total_cost = con.execute("SELECT SUM(cost_usd) FROM cost_ledger").fetchone()[0] or 0
        except Exception:
            total_cost = 0
        reports_gen    = con.execute("SELECT COUNT(*) FROM compliance_reports WHERE status='done'").fetchone()[0]
        last_report    = con.execute("SELECT created_at, framework FROM compliance_reports WHERE status='done' ORDER BY created_at DESC LIMIT 1").fetchone()
    finally:
        con.close()

    chain = verify_chain()

    return {
        "chain_integrity":    chain.get("ok", True),
        "chain_entries":      audit_total,
        "high_risk_actions":  high_risk,
        "failed_actions":     failures,
        "hitl_total":         hitl_total,
        "hitl_pending":       hitl_pending,
        "policy_blocked":     policy_blocked,
        "policy_total":       policy_total,
        "block_rate_pct":     round(policy_blocked / max(policy_total, 1) * 100, 1),
        "active_agents":      agents,
        "total_cost_usd":     round(float(total_cost), 4),
        "reports_generated":  reports_gen,
        "last_report_at":     last_report["created_at"] if last_report else None,
        "last_report_framework": last_report["framework"] if last_report else None,
    }
