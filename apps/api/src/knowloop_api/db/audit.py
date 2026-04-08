from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pydantic import BaseModel

from knowloop_api.core.config import Settings


class AuditEventRecord(BaseModel):
    event_id: str
    entity_type: str
    entity_id: str
    action: str
    actor_role: str
    actor_id: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    notes: str | None = None
    request_id: str | None = None
    idempotency_key: str | None = None
    created_at: datetime


class MutationRequestRecord(BaseModel):
    entity_type: str
    entity_id: str
    action: str
    idempotency_key: str
    actor_role: str
    actor_id: str | None = None
    request_fingerprint: str
    status: str
    created_at: datetime
    updated_at: datetime


def create_audit_event(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_role: str,
    actor_id: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    notes: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    created_at: datetime | None = None,
) -> AuditEventRecord:
    event_timestamp = created_at or datetime.now(UTC)
    event = AuditEventRecord(
        event_id=build_audit_event_id(
            action=action,
            entity_id=entity_id,
            created_at=event_timestamp,
        ),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_role=actor_role,
        actor_id=actor_id,
        from_status=from_status,
        to_status=to_status,
        notes=notes,
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=event_timestamp,
    )

    with sqlite3.connect(settings.audit_db_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    entity_type,
                    entity_id,
                    action,
                    actor_role,
                    actor_id,
                    from_status,
                    to_status,
                    notes,
                    request_id,
                    idempotency_key,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.entity_type,
                    event.entity_id,
                    event.action,
                    event.actor_role,
                    event.actor_id,
                    event.from_status,
                    event.to_status,
                    event.notes,
                    event.request_id,
                    event.idempotency_key,
                    event.created_at.isoformat().replace("+00:00", "Z"),
                ),
            )
        except sqlite3.IntegrityError:
            existing_event = get_audit_event(settings, event.event_id)
            if existing_event is None:
                raise
            return existing_event
        connection.commit()

    return event


def list_audit_events(
    settings: Settings,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    idempotency_key: str | None = None,
) -> list[AuditEventRecord]:
    query = """
        SELECT
            event_id,
            entity_type,
            entity_id,
            action,
            actor_role,
            actor_id,
            from_status,
            to_status,
            notes,
            request_id,
            idempotency_key,
            created_at
        FROM audit_events
    """
    clauses: list[str] = []
    parameters: list[str] = []

    if entity_type is not None:
        clauses.append("entity_type = ?")
        parameters.append(entity_type)
    if entity_id is not None:
        clauses.append("entity_id = ?")
        parameters.append(entity_id)
    if action is not None:
        clauses.append("action = ?")
        parameters.append(action)
    if idempotency_key is not None:
        clauses.append("idempotency_key = ?")
        parameters.append(idempotency_key)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY created_at DESC, event_id DESC"

    with sqlite3.connect(settings.audit_db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [
        AuditEventRecord(
            event_id=row[0],
            entity_type=row[1],
            entity_id=row[2],
            action=row[3],
            actor_role=row[4],
            actor_id=row[5],
            from_status=row[6],
            to_status=row[7],
            notes=row[8],
            request_id=row[9],
            idempotency_key=row[10],
            created_at=_parse_timestamp(row[11]),
        )
        for row in rows
    ]


def get_audit_event(settings: Settings, event_id: str) -> AuditEventRecord | None:
    with sqlite3.connect(settings.audit_db_path) as connection:
        row = connection.execute(
            """
            SELECT
                event_id,
                entity_type,
                entity_id,
                action,
                actor_role,
                actor_id,
                from_status,
                to_status,
                notes,
                request_id,
                idempotency_key,
                created_at
            FROM audit_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()

    if row is None:
        return None

    return AuditEventRecord(
        event_id=row[0],
        entity_type=row[1],
        entity_id=row[2],
        action=row[3],
        actor_role=row[4],
        actor_id=row[5],
        from_status=row[6],
        to_status=row[7],
        notes=row[8],
        request_id=row[9],
        idempotency_key=row[10],
        created_at=_parse_timestamp(row[11]),
    )


def get_mutation_request(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    idempotency_key: str,
) -> MutationRequestRecord | None:
    with sqlite3.connect(settings.audit_db_path) as connection:
        row = connection.execute(
            """
            SELECT
                entity_type,
                entity_id,
                action,
                idempotency_key,
                actor_role,
                actor_id,
                request_fingerprint,
                status,
                created_at,
                updated_at
            FROM mutation_requests
            WHERE entity_type = ?
              AND entity_id = ?
              AND action = ?
              AND idempotency_key = ?
            """,
            (entity_type, entity_id, action, idempotency_key),
        ).fetchone()

    if row is None:
        return None

    return MutationRequestRecord(
        entity_type=row[0],
        entity_id=row[1],
        action=row[2],
        idempotency_key=row[3],
        actor_role=row[4],
        actor_id=row[5],
        request_fingerprint=row[6],
        status=row[7],
        created_at=_parse_timestamp(row[8]),
        updated_at=_parse_timestamp(row[9]),
    )


def begin_mutation_request(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    idempotency_key: str,
    actor_role: str,
    actor_id: str | None,
    request_fingerprint: str,
    created_at: datetime,
) -> MutationRequestRecord:
    timestamp = created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO mutation_requests (
                entity_type,
                entity_id,
                action,
                idempotency_key,
                actor_role,
                actor_id,
                request_fingerprint,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                action,
                idempotency_key,
                actor_role,
                actor_id,
                request_fingerprint,
                "pending",
                timestamp,
                timestamp,
            ),
        )
        connection.commit()

    record = get_mutation_request(
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        idempotency_key=idempotency_key,
    )
    if record is None:
        raise RuntimeError("failed to create or load mutation request")
    return record


def mark_mutation_request_applied(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    idempotency_key: str,
    updated_at: datetime,
) -> MutationRequestRecord:
    existing_record = get_mutation_request(
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        idempotency_key=idempotency_key,
    )
    effective_updated_at = updated_at
    if existing_record is not None and existing_record.updated_at > effective_updated_at:
        effective_updated_at = existing_record.updated_at

    timestamp = effective_updated_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            """
            UPDATE mutation_requests
            SET status = ?, updated_at = ?
            WHERE entity_type = ?
              AND entity_id = ?
              AND action = ?
              AND idempotency_key = ?
            """,
            (
                "applied",
                timestamp,
                entity_type,
                entity_id,
                action,
                idempotency_key,
            ),
        )
        connection.commit()

    record = get_mutation_request(
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        idempotency_key=idempotency_key,
    )
    if record is None:
        raise RuntimeError("failed to update mutation request")
    return record


def build_audit_event_id(*, action: str, entity_id: str, created_at: datetime) -> str:
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"evt-{action}-{entity_id}-{timestamp}"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
