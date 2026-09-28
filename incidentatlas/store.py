"""Local durable telemetry/case storage. SQLite WAL; id conflicts never overwrite."""
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .normalize import canonical, epoch, normalize_payload


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, path=".incidentatlas/state.sqlite3"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS events (
            workspace TEXT NOT NULL, id TEXT NOT NULL, timestamp TEXT NOT NULL,
            service TEXT NOT NULL, trace_id TEXT, payload TEXT NOT NULL,
            fingerprint TEXT NOT NULL, late INTEGER NOT NULL DEFAULT 0,
            ingested_at TEXT NOT NULL, PRIMARY KEY (workspace,id));
          CREATE INDEX IF NOT EXISTS events_service_time ON events(workspace,service,timestamp);
          CREATE INDEX IF NOT EXISTS events_trace ON events(workspace,trace_id);
          CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,title TEXT NOT NULL,status TEXT NOT NULL,
            scenario_id TEXT, strategy TEXT NOT NULL, analysis TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES cases(id),
            body TEXT NOT NULL,created_at TEXT NOT NULL);
        """)
        # One Store is used by the serial reference server or via locked API calls.
        import threading
        self.lock = threading.RLock()

    def ingest(self, payload, workspace="demo"):
        if not isinstance(workspace, str) or not workspace or len(workspace) > 100:
            raise ValueError("workspace must be 1-100 characters")
        events, errors = normalize_payload(payload)
        result = {"accepted": 0, "duplicates": 0, "conflicts": 0, "invalid": len(errors), "late": 0, "errors": errors}
        with self.lock, self.db:
            row = self.db.execute("SELECT MAX(timestamp) FROM events WHERE workspace=?", (workspace,)).fetchone()
            high_water = epoch(row[0]) if row[0] else float("-inf")
            for event in events:
                fingerprint = canonical(event)
                old = self.db.execute("SELECT fingerprint FROM events WHERE workspace=? AND id=?", (workspace,event["id"])).fetchone()
                if old:
                    result["duplicates" if old[0] == fingerprint else "conflicts"] += 1
                    if old[0] != fingerprint:
                        result["errors"].append({"event_id": event["id"], "error": "id already exists with different content"})
                    continue
                t = epoch(event["timestamp"])
                late = t < high_water - 30
                high_water = max(high_water,t)
                self.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", (workspace,event["id"],event["timestamp"],event["service"],event.get("trace_id"),json.dumps(event),fingerprint,int(late),now()))
                result["accepted"] += 1
                result["late"] += int(late)
        return result

    def events(self, workspace="demo", start=None, end=None):
        if not isinstance(workspace, str) or not workspace or len(workspace) > 100:
            raise ValueError("workspace must be 1-100 characters")
        sql, args = "SELECT payload,late,ingested_at FROM events WHERE workspace=?", [workspace]
        for op,value in ((">=",start),("<=",end)):
            if value:
                sql += f" AND timestamp{op}?"
                args.append(value)
        with self.lock:
            rows = self.db.execute(sql + " ORDER BY timestamp,id",args).fetchall()
        return [{**json.loads(r[0]),"late":bool(r[1]),"ingested_at":r[2]} for r in rows]

    def create_case(self, title, analysis, scenario_id=None):
        from .engine import validate_analysis
        if not isinstance(title,str) or not title.strip() or len(title)>200:
            raise ValueError("case title must be 1-200 characters")
        validate_analysis(analysis)
        identifier, created = "case_"+uuid.uuid4().hex[:12], now()
        with self.lock,self.db:
            self.db.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)", (identifier,title.strip(),"open",scenario_id,analysis["strategy"],json.dumps(analysis),created,created))
        return self.case(identifier)

    def cases(self):
        with self.lock:
            rows = self.db.execute("SELECT c.id,title,status,scenario_id,strategy,c.created_at,updated_at,COUNT(n.id) AS note_count FROM cases c LEFT JOIN notes n ON n.case_id=c.id GROUP BY c.id ORDER BY c.created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def case(self, identifier):
        with self.lock:
            row = self.db.execute("SELECT * FROM cases WHERE id=?", (identifier,)).fetchone()
            if not row: raise KeyError("case not found")
            result = dict(row)
            result["analysis"] = json.loads(result["analysis"])
            result["notes"] = [dict(r) for r in self.db.execute("SELECT id,body,created_at FROM notes WHERE case_id=? ORDER BY created_at",(identifier,))]
        return result

    def update_case(self, identifier, status=None, note=None):
        if status is not None and status not in ("open","reviewing","resolved"):
            raise ValueError("status must be open, reviewing or resolved")
        if note is not None and (not isinstance(note,str) or not note.strip() or len(note)>5000):
            raise ValueError("note must be 1-5000 characters")
        with self.lock,self.db:
            self.case(identifier)
            if status is not None:
                self.db.execute("UPDATE cases SET status=?,updated_at=? WHERE id=?",(status,now(),identifier))
            if note is not None:
                self.db.execute("INSERT INTO notes VALUES (?,?,?,?)",("note_"+uuid.uuid4().hex[:12],identifier,note.strip(),now()))
                self.db.execute("UPDATE cases SET updated_at=? WHERE id=?",(now(),identifier))
        return self.case(identifier)

    def close(self):
        self.db.close()
