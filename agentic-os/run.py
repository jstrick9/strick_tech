#!/usr/bin/env python3
import os, sys, sqlite3, webbrowser, threading, time
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))
def init_db():
    db_path = ROOT / "memory" / "agentic.db"
    db_path.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, source TEXT, content TEXT, tags TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, tags, content='memory', content_rowid='id');
    CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY, title TEXT, layer TEXT, progress INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS chat_log (id INTEGER PRIMARY KEY, agent TEXT, role TEXT, message TEXT, tokens INTEGER DEFAULT 0, cost REAL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT DEFAULT 'todo', priority TEXT DEFAULT 'medium', agent TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, action TEXT, detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    """)
    if cur.execute("SELECT COUNT(*) FROM goals").fetchone()[0]==0:
        cur.executemany("INSERT INTO goals(title,layer,progress) VALUES (?,?,?)", [
            ("Launch Agentic OS locally","Vision",75),
            ("Connect Obsidian Self Layer","Goals",40),
            ("Enable Hermes autonomous loop","Tasks",15),
            ("Ship first multi-modal Studio export","Execution",5),
        ])
    if cur.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]==0:
        cur.executemany("INSERT INTO tasks(title,status,priority,agent) VALUES (?,?,?,?)", [
            ("Wire Claude Desktop bridge","doing","high","claude"),
            ("Index Obsidian vault","todo","high","hermes"),
            ("Test OpenClaw browser task","todo","medium","openclaw"),
            ("Build Studio image pipeline","todo","medium","gemini"),
            ("Daily self-reflect journal","todo","low","self"),
            ("Cost optimizer cron","blocked","low","hermes"),
        ])
    if cur.execute("SELECT COUNT(*) FROM memory").fetchone()[0]==0:
        cur.executemany("INSERT INTO memory(source,content,tags) VALUES (?,?,?)", [
            ("self","Agentic OS initialized. Shared memory active. Goldie Mission Stack online.","system,init"),
            ("vault","My business: Solo founder building AI automation agency. Focus: SEO, agent OS, content systems.","self,business"),
            ("hermes","Hermes autonomous loop ready. Scheduler: APScheduler cron enabled.","hermes,agent"),
        ])
        cur.execute("INSERT INTO memory_fts(rowid,content,tags) SELECT id, content, tags FROM memory")
    con.commit(); con.close()
def open_browser():
    time.sleep(1.3)
    try: webbrowser.open("http://localhost:8787")
    except: pass
if __name__ == "__main__":
    init_db()
    print("\n\033[95m╔══════════════════════════════════════════════╗\033[0m")
    print("\033[95m║          🧠 AGENTIC OS — MISSION CONTROL    ║\033[0m")
    print("\033[95m║  Free Boardroom Clone · Local-first · MIT   ║\033[0m")
    print("\033[95m╚══════════════════════════════════════════════╝\033[0m\n")
    print("  Agents: Swarm · Galaxy · Claude · Hermes · Builder · Expo · OpenClaw · Gemini · Grok")
    print("  Memory: Qdrant vector RAG + SQLite FTS5 — Secrets Vault + PM + Inspector + Swarm + Galaxy v5.0")
    print("  URL:    \033[96mhttp://localhost:8787\033[0m\n")
    threading.Thread(target=open_browser, daemon=True).start()
    import uvicorn
    uvicorn.run("app:app", app_dir=str(ROOT / "backend"), host="0.0.0.0", port=8787, reload=False, log_level="info")
