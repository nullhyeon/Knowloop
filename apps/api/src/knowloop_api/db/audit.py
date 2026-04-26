from __future__ import annotations

import hashlib
import json
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
    details: dict[str, object] | None = None
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
    response_payload: dict[str, object] | None = None
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
    details: dict[str, object] | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    created_at: datetime | None = None,
) -> AuditEventRecord:
    event_timestamp = created_at or datetime.now(UTC)
    event = _build_audit_event_record(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_role=actor_role,
        actor_id=actor_id,
        from_status=from_status,
        to_status=to_status,
        notes=notes,
        details=details,
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=event_timestamp,
    )

    with sqlite3.connect(settings.audit_db_path) as connection:
        for _attempt in range(5):
            try:
                _insert_audit_event(connection, event)
                connection.commit()
                return event
            except sqlite3.IntegrityError as exc:
                if not _is_audit_event_id_conflict(exc):
                    raise
                existing_event = _get_audit_event_in_connection(connection, event.event_id)
                if existing_event is not None and _audit_events_equivalent(existing_event, event):
                    return existing_event
                event = event.model_copy(
                    update={
                        "event_id": build_audit_event_id(
                            action=action,
                            entity_id=entity_id,
                            created_at=event_timestamp,
                            collision_suffix=_build_audit_event_collision_suffix(
                                event,
                                attempt=_attempt,
                            ),
                        )
                    }
                )
        raise RuntimeError("failed to allocate a unique audit event id")


def list_audit_events(
    settings: Settings,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
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
            details_json,
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
    if request_id is not None:
        clauses.append("request_id = ?")
        parameters.append(request_id)

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
            details=_parse_audit_details(row[9]),
            request_id=row[10],
            idempotency_key=row[11],
            created_at=_parse_timestamp(row[12]),
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
                details_json,
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
        details=_parse_audit_details(row[9]),
        request_id=row[10],
        idempotency_key=row[11],
        created_at=_parse_timestamp(row[12]),
    )


def update_audit_event_details(
    settings: Settings,
    *,
    event_id: str,
    details: dict[str, object],
) -> AuditEventRecord | None:
    serialized_details = _serialize_audit_details(details)
    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            """
            UPDATE audit_events
            SET details_json = ?
            WHERE event_id = ?
            """,
            (serialized_details, event_id),
        )
        connection.commit()

    return get_audit_event(settings, event_id)


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
                response_json,
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
        response_payload=_parse_audit_details(row[8]),
        created_at=_parse_timestamp(row[9]),
        updated_at=_parse_timestamp(row[10]),
    )


def list_mutation_requests(
    settings: Settings,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    request_fingerprint: str | None = None,
    status: str | None = None,
) -> list[MutationRequestRecord]:
    query = """
        SELECT
            entity_type,
            entity_id,
            action,
            idempotency_key,
            actor_role,
            actor_id,
            request_fingerprint,
            status,
            response_json,
            created_at,
            updated_at
        FROM mutation_requests
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
    if request_fingerprint is not None:
        clauses.append("request_fingerprint = ?")
        parameters.append(request_fingerprint)
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY created_at DESC, idempotency_key DESC"

    with sqlite3.connect(settings.audit_db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [
        MutationRequestRecord(
            entity_type=row[0],
            entity_id=row[1],
            action=row[2],
            idempotency_key=row[3],
            actor_role=row[4],
            actor_id=row[5],
            request_fingerprint=row[6],
            status=row[7],
            response_payload=_parse_audit_details(row[8]),
            created_at=_parse_timestamp(row[9]),
            updated_at=_parse_timestamp(row[10]),
        )
        for row in rows
    ]


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
                response_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                None,
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
    response_payload: dict[str, object] | None = None,
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
            SET status = ?, response_json = ?, updated_at = ?
            WHERE entity_type = ?
              AND entity_id = ?
              AND action = ?
              AND idempotency_key = ?
            """,
            (
                "applied",
                _serialize_audit_details(response_payload),
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


def store_mutation_request_response_payload(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    idempotency_key: str,
    updated_at: datetime,
    response_payload: dict[str, object],
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
            SET response_json = ?, updated_at = ?
            WHERE entity_type = ?
              AND entity_id = ?
              AND action = ?
              AND idempotency_key = ?
            """,
            (
                _serialize_audit_details(response_payload),
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
        raise RuntimeError("failed to update mutation request response payload")
    return record


def touch_mutation_request(
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
            SET updated_at = ?
            WHERE entity_type = ?
              AND entity_id = ?
              AND action = ?
              AND idempotency_key = ?
            """,
            (
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
        raise RuntimeError("failed to touch mutation request")
    return record


def reclaim_stale_mutation_request(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    idempotency_key: str,
    request_fingerprint: str,
    cutoff_updated_at: datetime,
    reclaimed_at: datetime,
) -> MutationRequestRecord | None:
    cutoff_timestamp = cutoff_updated_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    reclaimed_timestamp = reclaimed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(settings.audit_db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE mutation_requests
            SET updated_at = ?
            WHERE entity_type = ?
              AND entity_id = ?
              AND action = ?
              AND idempotency_key = ?
              AND request_fingerprint = ?
              AND status = 'pending'
              AND response_json IS NULL
              AND updated_at <= ?
            """,
            (
                reclaimed_timestamp,
                entity_type,
                entity_id,
                action,
                idempotency_key,
                request_fingerprint,
                cutoff_timestamp,
            ),
        )
        connection.commit()
        if cursor.rowcount != 1:
            return None

    return get_mutation_request(
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        idempotency_key=idempotency_key,
    )


def build_audit_event_id(
    *,
    action: str,
    entity_id: str,
    created_at: datetime,
    collision_suffix: str | None = None,
) -> str:
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    base_event_id = f"evt-{action}-{entity_id}-{timestamp}"
    if collision_suffix is None:
        return base_event_id
    return f"{base_event_id}-{collision_suffix}"


def _build_audit_event_record(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_role: str,
    actor_id: str | None,
    from_status: str | None,
    to_status: str | None,
    notes: str | None,
    details: dict[str, object] | None,
    request_id: str | None,
    idempotency_key: str | None,
    created_at: datetime,
) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=build_audit_event_id(
            action=action,
            entity_id=entity_id,
            created_at=created_at,
        ),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_role=actor_role,
        actor_id=actor_id,
        from_status=from_status,
        to_status=to_status,
        notes=notes,
        details=details,
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=created_at,
    )


def _insert_audit_event(connection: sqlite3.Connection, event: AuditEventRecord) -> None:
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
            details_json,
            request_id,
            idempotency_key,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            _serialize_audit_details(event.details),
            event.request_id,
            event.idempotency_key,
            event.created_at.isoformat().replace("+00:00", "Z"),
        ),
    )


def _get_audit_event_in_connection(
    connection: sqlite3.Connection,
    event_id: str,
) -> AuditEventRecord | None:
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
            details_json,
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
        details=_parse_audit_details(row[9]),
        request_id=row[10],
        idempotency_key=row[11],
        created_at=_parse_timestamp(row[12]),
    )


def _audit_events_equivalent(
    existing_event: AuditEventRecord,
    candidate_event: AuditEventRecord,
) -> bool:
    return existing_event.model_dump(exclude={"event_id"}) == candidate_event.model_dump(
        exclude={"event_id"}
    )


def _is_audit_event_id_conflict(error: sqlite3.IntegrityError) -> bool:
    message = str(error).lower()
    return "unique constraint failed" in message and "audit_events.event_id" in message


def _build_audit_event_collision_suffix(
    event: AuditEventRecord,
    *,
    attempt: int,
) -> str:
    digest = hashlib.sha1(
        json.dumps(
            event.model_dump(mode="json", exclude={"event_id"}, exclude_none=False),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    if attempt == 0:
        return digest
    return f"{digest}-{attempt}"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _serialize_audit_details(details: dict[str, object] | None) -> str | None:
    if details is None:
        return None
    return json.dumps(details, sort_keys=True, separators=(",", ":"))


def _parse_audit_details(value: str | None) -> dict[str, object] | None:
    if value is None:
        return None
    return json.loads(value)
