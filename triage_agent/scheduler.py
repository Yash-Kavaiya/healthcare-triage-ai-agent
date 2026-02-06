from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .config import TriageConfig
from .database import SQLiteRepository, utc_now
from .models import AppointmentResult, Urgency


@dataclass
class Scheduler:
    repository: SQLiteRepository
    config: TriageConfig

    def book(
        self,
        *,
        patient_id: int,
        triage_event_id: int,
        urgency: Urgency,
        department: str,
        note: str,
        allow_preemption: bool = True,
    ) -> AppointmentResult:
        now = utc_now()
        window_minutes = self.config.urgency_windows_minutes[urgency.value]
        window_end = now + timedelta(minutes=window_minutes)
        fallback_end = now + timedelta(minutes=self.config.fallback_window_minutes)

        with self.repository.connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            slot = self.repository.find_available_slot(
                department=department,
                start_at=now,
                end_at=window_end,
                conn=conn,
            )
            if slot:
                appointment_id = self.repository.create_appointment(
                    patient_id=patient_id,
                    triage_event_id=triage_event_id,
                    urgency=urgency.value,
                    department=department,
                    provider=slot["provider"],
                    slot_id=slot["id"],
                    note=note,
                    conn=conn,
                )
                return AppointmentResult(
                    status="BOOKED",
                    appointment_id=appointment_id,
                    slot_id=slot["id"],
                    slot_start=slot["start_at"],
                    note=note,
                )

            if urgency in (Urgency.SOON, Urgency.ROUTINE):
                fallback_slot = self.repository.find_next_available_slot(
                    department=department,
                    start_at=window_end,
                    end_at=fallback_end,
                    conn=conn,
                )
                if fallback_slot:
                    fallback_note = f"{note} | booked outside ideal urgency window"
                    appointment_id = self.repository.create_appointment(
                        patient_id=patient_id,
                        triage_event_id=triage_event_id,
                        urgency=urgency.value,
                        department=department,
                        provider=fallback_slot["provider"],
                        slot_id=fallback_slot["id"],
                        note=fallback_note,
                        conn=conn,
                    )
                    return AppointmentResult(
                        status="BOOKED_FALLBACK",
                        appointment_id=appointment_id,
                        slot_id=fallback_slot["id"],
                        slot_start=fallback_slot["start_at"],
                        note=fallback_note,
                    )
                return AppointmentResult(
                    status="ESCALATED",
                    note="No available slots found within fallback window.",
                )

            if not (allow_preemption and self.config.preemption_enabled):
                return AppointmentResult(
                    status="ESCALATED",
                    note="No available slot in urgency window and preemption disabled.",
                )

            candidate = self.repository.find_preemptable_appointment(
                department=department,
                higher_urgency=urgency.value,
                window_end=window_end,
                conn=conn,
            )
            if not candidate:
                return AppointmentResult(
                    status="ESCALATED",
                    note="No lower-priority appointment available for preemption.",
                )

            replacement_slot = self.repository.find_next_available_slot(
                department=department,
                start_at=window_end,
                end_at=fallback_end,
                conn=conn,
            )
            if not replacement_slot:
                return AppointmentResult(
                    status="ESCALATED",
                    note="Preemption blocked: could not safely reschedule the preempted patient.",
                )

            self.repository.move_appointment_to_slot(
                appointment_id=int(candidate["appointment_id"]),
                new_slot_id=int(replacement_slot["id"]),
                note=(
                    "Preempted by higher-priority case; auto-rescheduled to "
                    f"{replacement_slot['start_at']}"
                ),
                conn=conn,
            )

            preempted_slot = self.repository.get_slot(int(candidate["slot_id"]), conn=conn)
            if not preempted_slot:
                raise RuntimeError("Preempted slot lookup failed.")

            appointment_id = self.repository.create_appointment(
                patient_id=patient_id,
                triage_event_id=triage_event_id,
                urgency=urgency.value,
                department=department,
                provider=preempted_slot["provider"],
                slot_id=preempted_slot["id"],
                note=f"{note} | preemption applied",
                preempted_from_appointment_id=int(candidate["appointment_id"]),
                conn=conn,
            )
            self.repository.log_appointment_activity(
                appointment_id=int(candidate["appointment_id"]),
                activity_type="PREEMPTED_OUT",
                details={
                    "by_appointment_id": appointment_id,
                    "new_slot_id": replacement_slot["id"],
                },
                conn=conn,
            )
            self.repository.log_appointment_activity(
                appointment_id=appointment_id,
                activity_type="PREEMPTED_IN",
                details={
                    "preempted_appointment_id": candidate["appointment_id"],
                    "slot_id": preempted_slot["id"],
                },
                conn=conn,
            )
            return AppointmentResult(
                status="PREEMPTED",
                appointment_id=appointment_id,
                slot_id=preempted_slot["id"],
                slot_start=preempted_slot["start_at"],
                note="Booked by preempting a lower-priority case.",
                preempted_appointment_id=int(candidate["appointment_id"]),
            )
