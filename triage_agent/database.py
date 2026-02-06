from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import TriageConfig
from .models import RoutingDecision, TriageResult, urgency_rank

DB_TIME_FMT = "%Y-%m-%d %H:%M:%S"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def to_db_time(value: datetime) -> str:
    return value.strftime(DB_TIME_FMT)


def parse_db_time(value: str) -> datetime:
    return datetime.strptime(value, DB_TIME_FMT)


class SQLiteRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def _managed_conn(self, conn: sqlite3.Connection | None):
        if conn is not None:
            yield conn
            return
        with self.connect() as local_conn:
            yield local_conn

    def init_db(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            age INTEGER NOT NULL,
            sex TEXT NOT NULL,
            symptoms TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS triage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            redacted_symptoms TEXT NOT NULL,
            urgency TEXT NOT NULL,
            confidence REAL NOT NULL,
            red_flags TEXT NOT NULL,
            department_candidates TEXT NOT NULL,
            suggested_department TEXT NOT NULL,
            rationale TEXT NOT NULL,
            recommended_timeframe_minutes INTEGER NOT NULL,
            human_routing_flag INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS routing_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            triage_event_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            confidence_threshold REAL NOT NULL,
            department_threshold REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(triage_event_id) REFERENCES triage_events(id)
        );

        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department TEXT NOT NULL,
            provider TEXT NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'AVAILABLE',
            appointment_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            triage_event_id INTEGER NOT NULL,
            urgency TEXT NOT NULL,
            department TEXT NOT NULL,
            provider TEXT NOT NULL,
            slot_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'BOOKED',
            note TEXT,
            booked_at TEXT NOT NULL DEFAULT (datetime('now')),
            preempted_from_appointment_id INTEGER,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(triage_event_id) REFERENCES triage_events(id),
            FOREIGN KEY(slot_id) REFERENCES slots(id)
        );

        CREATE TABLE IF NOT EXISTS nurse_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            triage_event_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reason TEXT NOT NULL,
            priority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT,
            assigned_to TEXT,
            notes TEXT,
            FOREIGN KEY(triage_event_id) REFERENCES triage_events(id)
        );

        CREATE TABLE IF NOT EXISTS appointment_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL,
            activity_type TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(appointment_id) REFERENCES appointments(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_slots_lookup
            ON slots(department, status, start_at);
        CREATE INDEX IF NOT EXISTS idx_queue_status
            ON nurse_queue(status, priority, created_at);
        CREATE INDEX IF NOT EXISTS idx_appointments_patient
            ON appointments(patient_id, booked_at);
        """
        with self.connect() as conn:
            conn.executescript(schema)

    def seed_slots_if_empty(self, config: TriageConfig) -> None:
        with self.connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM slots;")
            slot_count = cur.fetchone()[0]
            if slot_count > 0:
                return

            now = utc_now()
            for day in range(config.seed_days):
                date = (now + timedelta(days=day)).date()
                for department, providers in config.department_providers.items():
                    provider_count = len(providers)
                    for hour in range(9, 17):
                        start_at = datetime(
                            year=date.year,
                            month=date.month,
                            day=date.day,
                            hour=hour,
                            minute=0,
                            second=0,
                        )
                        end_at = start_at + timedelta(minutes=45)
                        provider = providers[(hour + day) % provider_count]
                        conn.execute(
                            """
                            INSERT INTO slots (
                                department, provider, start_at, end_at, status
                            ) VALUES (?, ?, ?, ?, 'AVAILABLE');
                            """,
                            (
                                department,
                                provider,
                                to_db_time(start_at),
                                to_db_time(end_at),
                            ),
                        )

    def create_patient(
        self,
        *,
        phone: str | None,
        age: int,
        sex: str,
        symptoms: str,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._managed_conn(conn) as db:
            cur = db.execute(
                """
                INSERT INTO patients (phone, age, sex, symptoms)
                VALUES (?, ?, ?, ?);
                """,
                (phone, age, sex, symptoms),
            )
            return int(cur.lastrowid)

    def create_triage_event(
        self,
        *,
        patient_id: int,
        triage_result: TriageResult,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._managed_conn(conn) as db:
            cur = db.execute(
                """
                INSERT INTO triage_events (
                    patient_id,
                    redacted_symptoms,
                    urgency,
                    confidence,
                    red_flags,
                    department_candidates,
                    suggested_department,
                    rationale,
                    recommended_timeframe_minutes,
                    human_routing_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    patient_id,
                    triage_result.redacted_symptoms,
                    triage_result.urgency.value,
                    triage_result.confidence,
                    json.dumps(triage_result.red_flags),
                    json.dumps(
                        [
                            {"department": d.department, "score": d.score}
                            for d in triage_result.department_candidates
                        ]
                    ),
                    triage_result.suggested_department,
                    triage_result.rationale,
                    triage_result.recommended_timeframe_minutes,
                    int(triage_result.human_routing_flag),
                ),
            )
            return int(cur.lastrowid)

    def create_routing_decision(
        self,
        *,
        triage_event_id: int,
        decision: RoutingDecision,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._managed_conn(conn) as db:
            cur = db.execute(
                """
                INSERT INTO routing_decisions (
                    triage_event_id,
                    action,
                    reason,
                    confidence_threshold,
                    department_threshold
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    triage_event_id,
                    decision.action.value,
                    decision.reason,
                    decision.confidence_threshold,
                    decision.department_threshold,
                ),
            )
            return int(cur.lastrowid)

    def enqueue_case(
        self,
        *,
        triage_event_id: int,
        reason: str,
        priority: str,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._managed_conn(conn) as db:
            cur = db.execute(
                """
                INSERT INTO nurse_queue (triage_event_id, reason, priority)
                VALUES (?, ?, ?);
                """,
                (triage_event_id, reason, priority),
            )
            queue_id = int(cur.lastrowid)
            self.audit(
                entity_type="nurse_queue",
                entity_id=queue_id,
                action="ENQUEUED",
                payload={"reason": reason, "priority": priority},
                conn=db,
            )
            return queue_id

    def resolve_queue_item(
        self,
        *,
        queue_id: int,
        status: str,
        notes: str,
        assigned_to: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        with self._managed_conn(conn) as db:
            db.execute(
                """
                UPDATE nurse_queue
                SET status = ?, notes = ?, assigned_to = ?, resolved_at = datetime('now')
                WHERE id = ?;
                """,
                (status, notes, assigned_to, queue_id),
            )
            self.audit(
                entity_type="nurse_queue",
                entity_id=queue_id,
                action="RESOLVED",
                payload={"status": status, "notes": notes, "assigned_to": assigned_to},
                conn=db,
            )

    def get_queue_item(self, queue_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    q.*,
                    t.patient_id,
                    t.urgency,
                    t.suggested_department
                FROM nurse_queue q
                JOIN triage_events t ON t.id = q.triage_event_id
                WHERE q.id = ?;
                """,
                (queue_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_queue(self, *, status: str = "PENDING", limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    q.id,
                    q.status,
                    q.priority,
                    q.reason,
                    q.created_at,
                    q.triage_event_id,
                    t.urgency,
                    t.confidence,
                    t.suggested_department,
                    t.rationale,
                    p.id AS patient_id,
                    p.phone,
                    p.age,
                    p.sex,
                    p.symptoms
                FROM nurse_queue q
                JOIN triage_events t ON t.id = q.triage_event_id
                JOIN patients p ON p.id = t.patient_id
                WHERE q.status = ?
                ORDER BY
                    CASE q.priority
                        WHEN 'EMERGENCY' THEN 4
                        WHEN 'URGENT' THEN 3
                        WHEN 'SOON' THEN 2
                        ELSE 1
                    END DESC,
                    q.created_at ASC
                LIMIT ?;
                """,
                (status, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_slot(
        self,
        *,
        department: str,
        provider: str,
        start_at: datetime,
        end_at: datetime,
        status: str = "AVAILABLE",
        appointment_id: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._managed_conn(conn) as db:
            cur = db.execute(
                """
                INSERT INTO slots (
                    department, provider, start_at, end_at, status, appointment_id
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    department,
                    provider,
                    to_db_time(start_at),
                    to_db_time(end_at),
                    status,
                    appointment_id,
                ),
            )
            return int(cur.lastrowid)

    def get_slot(
        self, slot_id: int, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any] | None:
        with self._managed_conn(conn) as db:
            row = db.execute("SELECT * FROM slots WHERE id = ?;", (slot_id,)).fetchone()
            return dict(row) if row else None

    def find_available_slot(
        self,
        *,
        department: str,
        start_at: datetime,
        end_at: datetime,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._managed_conn(conn) as db:
            row = db.execute(
                """
                SELECT *
                FROM slots
                WHERE department = ?
                  AND status = 'AVAILABLE'
                  AND start_at >= ?
                  AND start_at <= ?
                ORDER BY start_at ASC
                LIMIT 1;
                """,
                (department, to_db_time(start_at), to_db_time(end_at)),
            ).fetchone()
            return dict(row) if row else None

    def find_next_available_slot(
        self,
        *,
        department: str,
        start_at: datetime,
        end_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT *
            FROM slots
            WHERE department = ?
              AND status = 'AVAILABLE'
              AND start_at >= ?
        """
        params: list[Any] = [department, to_db_time(start_at)]
        if end_at is not None:
            query += " AND start_at <= ?"
            params.append(to_db_time(end_at))
        query += " ORDER BY start_at ASC LIMIT 1;"

        with self._managed_conn(conn) as db:
            row = db.execute(query, tuple(params)).fetchone()
            return dict(row) if row else None

    def find_preemptable_appointment(
        self,
        *,
        department: str,
        higher_urgency: str,
        window_end: datetime,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._managed_conn(conn) as db:
            rows = db.execute(
                """
                SELECT
                    a.id AS appointment_id,
                    a.patient_id,
                    a.urgency,
                    a.slot_id,
                    s.start_at,
                    s.end_at,
                    s.provider
                FROM appointments a
                JOIN slots s ON s.id = a.slot_id
                WHERE a.status = 'BOOKED'
                  AND a.department = ?
                  AND s.start_at <= ?
                ORDER BY s.start_at ASC;
                """,
                (department, to_db_time(window_end)),
            ).fetchall()
            if not rows:
                return None

            higher_rank = urgency_rank(higher_urgency)
            candidates = []
            for row in rows:
                row_rank = urgency_rank(row["urgency"])
                if row_rank < higher_rank:
                    candidates.append(dict(row))
            if not candidates:
                return None

            candidates.sort(
                key=lambda item: (urgency_rank(item["urgency"]), item["start_at"])
            )
            return candidates[0]

    def create_appointment(
        self,
        *,
        patient_id: int,
        triage_event_id: int,
        urgency: str,
        department: str,
        provider: str,
        slot_id: int,
        note: str,
        preempted_from_appointment_id: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._managed_conn(conn) as db:
            updated = db.execute(
                """
                UPDATE slots
                SET status = 'BOOKED'
                WHERE id = ? AND status = 'AVAILABLE';
                """,
                (slot_id,),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Slot is no longer available.")

            cur = db.execute(
                """
                INSERT INTO appointments (
                    patient_id,
                    triage_event_id,
                    urgency,
                    department,
                    provider,
                    slot_id,
                    status,
                    note,
                    preempted_from_appointment_id
                )
                VALUES (?, ?, ?, ?, ?, ?, 'BOOKED', ?, ?);
                """,
                (
                    patient_id,
                    triage_event_id,
                    urgency,
                    department,
                    provider,
                    slot_id,
                    note,
                    preempted_from_appointment_id,
                ),
            )
            appointment_id = int(cur.lastrowid)
            db.execute(
                "UPDATE slots SET appointment_id = ? WHERE id = ?;",
                (appointment_id, slot_id),
            )
            self.log_appointment_activity(
                appointment_id=appointment_id,
                activity_type="BOOKED",
                details={"slot_id": slot_id, "note": note, "urgency": urgency},
                conn=db,
            )
            self.audit(
                entity_type="appointments",
                entity_id=appointment_id,
                action="BOOKED",
                payload={
                    "slot_id": slot_id,
                    "department": department,
                    "urgency": urgency,
                    "preempted_from_appointment_id": preempted_from_appointment_id,
                },
                conn=db,
            )
            return appointment_id

    def move_appointment_to_slot(
        self,
        *,
        appointment_id: int,
        new_slot_id: int,
        note: str,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        with self._managed_conn(conn) as db:
            appt = db.execute(
                """
                SELECT slot_id, provider, note
                FROM appointments
                WHERE id = ? AND status = 'BOOKED';
                """,
                (appointment_id,),
            ).fetchone()
            if not appt:
                raise RuntimeError("Booked appointment not found for move.")

            new_slot = db.execute(
                """
                SELECT id, provider, status
                FROM slots
                WHERE id = ?;
                """,
                (new_slot_id,),
            ).fetchone()
            if not new_slot:
                raise RuntimeError("Target slot not found for move.")
            if new_slot["status"] != "AVAILABLE":
                raise RuntimeError("Target slot is not available for move.")

            old_slot_id = int(appt["slot_id"])
            old_note = appt["note"] or ""

            db.execute(
                """
                UPDATE slots
                SET status = 'AVAILABLE', appointment_id = NULL
                WHERE id = ?;
                """,
                (old_slot_id,),
            )
            db.execute(
                """
                UPDATE slots
                SET status = 'BOOKED', appointment_id = ?
                WHERE id = ?;
                """,
                (appointment_id, new_slot_id),
            )
            db.execute(
                """
                UPDATE appointments
                SET slot_id = ?, provider = ?, note = ?
                WHERE id = ?;
                """,
                (
                    new_slot_id,
                    new_slot["provider"],
                    (old_note + " | " + note).strip(" |"),
                    appointment_id,
                ),
            )
            self.log_appointment_activity(
                appointment_id=appointment_id,
                activity_type="RESCHEDULED",
                details={
                    "old_slot_id": old_slot_id,
                    "new_slot_id": new_slot_id,
                    "note": note,
                },
                conn=db,
            )
            self.audit(
                entity_type="appointments",
                entity_id=appointment_id,
                action="RESCHEDULED",
                payload={
                    "old_slot_id": old_slot_id,
                    "new_slot_id": new_slot_id,
                    "note": note,
                },
                conn=db,
            )

    def log_appointment_activity(
        self,
        *,
        appointment_id: int,
        activity_type: str,
        details: dict[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> None:
        with self._managed_conn(conn) as db:
            db.execute(
                """
                INSERT INTO appointment_activity (appointment_id, activity_type, details)
                VALUES (?, ?, ?);
                """,
                (appointment_id, activity_type, json.dumps(details)),
            )

    def audit(
        self,
        *,
        entity_type: str,
        entity_id: int,
        action: str,
        payload: dict[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> None:
        with self._managed_conn(conn) as db:
            db.execute(
                """
                INSERT INTO audit_log (entity_type, entity_id, action, payload)
                VALUES (?, ?, ?, ?);
                """,
                (entity_type, entity_id, action, json.dumps(payload)),
            )

    def get_patient(self, patient_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM patients WHERE id = ?;",
                (patient_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_triage_event(self, triage_event_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM triage_events WHERE id = ?;",
                (triage_event_id,),
            ).fetchone()
            if not row:
                return None
            event = dict(row)
            event["red_flags"] = json.loads(event["red_flags"])
            event["department_candidates"] = json.loads(event["department_candidates"])
            return event

    def get_appointment(
        self, appointment_id: int, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any] | None:
        with self._managed_conn(conn) as db:
            row = db.execute(
                """
                SELECT
                    a.*,
                    s.start_at,
                    s.end_at
                FROM appointments a
                JOIN slots s ON s.id = a.slot_id
                WHERE a.id = ?;
                """,
                (appointment_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_departments(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT department FROM slots ORDER BY department ASC;"
            ).fetchall()
            return [row["department"] for row in rows]

    def dashboard_metrics(self) -> dict[str, int | float]:
        with self.connect() as conn:
            total_slots = conn.execute("SELECT COUNT(*) FROM slots;").fetchone()[0]
            available_slots = conn.execute(
                "SELECT COUNT(*) FROM slots WHERE status = 'AVAILABLE';"
            ).fetchone()[0]
            booked_slots = int(total_slots) - int(available_slots)
            slot_utilization_percent = (
                round((booked_slots / int(total_slots)) * 100, 1) if int(total_slots) > 0 else 0.0
            )
            repeat_patients = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT patient_id
                    FROM appointments
                    GROUP BY patient_id
                    HAVING COUNT(*) > 1
                ) t;
                """
            ).fetchone()[0]
            pending_queue = conn.execute(
                "SELECT COUNT(*) FROM nurse_queue WHERE status = 'PENDING';"
            ).fetchone()[0]
            pending_high_priority_queue = conn.execute(
                """
                SELECT COUNT(*)
                FROM nurse_queue
                WHERE status = 'PENDING'
                  AND priority IN ('EMERGENCY', 'URGENT');
                """
            ).fetchone()[0]
            total_appointments = conn.execute(
                "SELECT COUNT(*) FROM appointments;"
            ).fetchone()[0]
            auto_booked_appointments = conn.execute(
                """
                SELECT COUNT(*)
                FROM appointments
                WHERE note LIKE 'Auto-booked from intake.%';
                """
            ).fetchone()[0]
            preempted_appointments = conn.execute(
                """
                SELECT COUNT(*)
                FROM appointments
                WHERE preempted_from_appointment_id IS NOT NULL;
                """
            ).fetchone()[0]
            triage_events_24h = conn.execute(
                """
                SELECT COUNT(*)
                FROM triage_events
                WHERE created_at >= datetime('now', '-24 hours');
                """
            ).fetchone()[0]
            urgent_cases_24h = conn.execute(
                """
                SELECT COUNT(*)
                FROM triage_events
                WHERE created_at >= datetime('now', '-24 hours')
                  AND urgency IN ('EMERGENCY', 'URGENT');
                """
            ).fetchone()[0]
            avg_confidence_24h_raw = conn.execute(
                """
                SELECT AVG(confidence)
                FROM triage_events
                WHERE created_at >= datetime('now', '-24 hours');
                """
            ).fetchone()[0]
            avg_confidence_24h = round(float(avg_confidence_24h_raw or 0.0), 3)
            return {
                "repeat_patients_in_slots": int(repeat_patients),
                "total_slots": int(total_slots),
                "available_slots": int(available_slots),
                "booked_slots": int(booked_slots),
                "slot_utilization_percent": float(slot_utilization_percent),
                "pending_queue": int(pending_queue),
                "pending_high_priority_queue": int(pending_high_priority_queue),
                "total_appointments": int(total_appointments),
                "auto_booked_appointments": int(auto_booked_appointments),
                "preempted_appointments": int(preempted_appointments),
                "triage_events_24h": int(triage_events_24h),
                "urgent_cases_24h": int(urgent_cases_24h),
                "avg_confidence_24h": float(avg_confidence_24h),
            }

    def recent_appointments(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.booked_at,
                    a.id AS appointment_id,
                    p.id AS patient_id,
                    p.phone,
                    a.urgency,
                    a.department,
                    a.provider,
                    a.slot_id,
                    s.start_at AS slot_start,
                    s.end_at AS slot_end,
                    a.note
                FROM appointments a
                JOIN patients p ON p.id = a.patient_id
                JOIN slots s ON s.id = a.slot_id
                ORDER BY a.id DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_activity(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, appointment_id, activity_type, details, created_at
                FROM appointment_activity
                ORDER BY id DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            output = []
            for row in rows:
                item = dict(row)
                item["details"] = json.loads(item["details"])
                output.append(item)
            return output

    def recent_triage_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.id AS triage_event_id,
                    t.created_at,
                    t.urgency,
                    t.confidence,
                    t.suggested_department,
                    t.human_routing_flag,
                    r.action AS routing_action,
                    r.reason AS routing_reason,
                    p.id AS patient_id,
                    p.phone,
                    p.age,
                    p.sex,
                    p.symptoms
                FROM triage_events t
                LEFT JOIN routing_decisions r ON r.triage_event_id = t.id
                JOIN patients p ON p.id = t.patient_id
                ORDER BY t.id DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_audit_log(
        self,
        *,
        limit: int = 100,
        entity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if entity_type:
                rows = conn.execute(
                    """
                    SELECT id, entity_type, entity_id, action, payload, created_at
                    FROM audit_log
                    WHERE entity_type = ?
                    ORDER BY id DESC
                    LIMIT ?;
                    """,
                    (entity_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, entity_type, entity_id, action, payload, created_at
                    FROM audit_log
                    ORDER BY id DESC
                    LIMIT ?;
                    """,
                    (limit,),
                ).fetchall()
            parsed: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                try:
                    item["payload"] = json.loads(item["payload"])
                except json.JSONDecodeError:
                    pass
                parsed.append(item)
            return parsed
