from datetime import timedelta

from triage_agent.config import TriageConfig
from triage_agent.database import SQLiteRepository, utc_now
from triage_agent.models import Urgency
from triage_agent.scheduler import Scheduler


def _setup_repo(tmp_path):
    db_file = tmp_path / "triage_test.db"
    repo = SQLiteRepository(str(db_file))
    repo.init_db()
    return repo


def _seed_patient_and_triage(repo: SQLiteRepository):
    with repo.connect() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        patient_id = repo.create_patient(
            phone=None,
            age=30,
            sex="Other",
            symptoms="test symptoms",
            conn=conn,
        )
        triage_event_id = conn.execute(
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
            ) VALUES (?, 'test symptoms', 'SOON', 0.9, '[]', '[]', 'General Medicine', 'test', 60, 0);
            """,
            (patient_id,),
        ).lastrowid
        return int(patient_id), int(triage_event_id)


def test_scheduler_books_available_slot(tmp_path) -> None:
    repo = _setup_repo(tmp_path)
    config = TriageConfig(db_path=str(tmp_path / "triage_test.db"))
    scheduler = Scheduler(repository=repo, config=config)

    now = utc_now()
    with repo.connect() as conn:
        repo.create_slot(
            department="General Medicine",
            provider="Dr. Test",
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=3),
            conn=conn,
        )

    patient_id, triage_event_id = _seed_patient_and_triage(repo)
    result = scheduler.book(
        patient_id=patient_id,
        triage_event_id=triage_event_id,
        urgency=Urgency.SOON,
        department="General Medicine",
        note="test book",
    )
    assert result.status == "BOOKED"
    assert result.appointment_id is not None


def test_scheduler_preempts_lower_priority_case(tmp_path) -> None:
    repo = _setup_repo(tmp_path)
    config = TriageConfig(db_path=str(tmp_path / "triage_test.db"))
    scheduler = Scheduler(repository=repo, config=config)
    now = utc_now()

    with repo.connect() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        low_patient = repo.create_patient(
            phone=None,
            age=45,
            sex="Male",
            symptoms="routine follow up",
            conn=conn,
        )
        low_triage_event = conn.execute(
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
            ) VALUES (?, 'routine follow up', 'ROUTINE', 0.9, '[]', '[]', 'Cardiology', 'test', 120, 0);
            """,
            (low_patient,),
        ).lastrowid

        preemptable_slot = repo.create_slot(
            department="Cardiology",
            provider="Dr. One",
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            conn=conn,
        )
        repo.create_appointment(
            patient_id=int(low_patient),
            triage_event_id=int(low_triage_event),
            urgency="ROUTINE",
            department="Cardiology",
            provider="Dr. One",
            slot_id=preemptable_slot,
            note="low priority",
            conn=conn,
        )

        repo.create_slot(
            department="Cardiology",
            provider="Dr. Two",
            start_at=now + timedelta(days=3),
            end_at=now + timedelta(days=3, hours=1),
            conn=conn,
        )

    high_patient, high_triage_event = _seed_patient_and_triage(repo)
    result = scheduler.book(
        patient_id=high_patient,
        triage_event_id=high_triage_event,
        urgency=Urgency.URGENT,
        department="Cardiology",
        note="urgent book",
        allow_preemption=True,
    )
    assert result.status == "PREEMPTED"
    assert result.preempted_appointment_id is not None
