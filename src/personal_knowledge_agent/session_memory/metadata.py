from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ..schemas import SessionMetadata

DEFAULT_SESSION_TITLE = "新会话"
TITLE_PREVIEW_CHARS = 30
TITLE_MAX_CHARS = 80
METADATA_JSON_INDENT = 2
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VALID_TITLE_SOURCES = {"auto", "user"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def validate_session_id(session_id: str) -> str:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id must contain only letters, numbers, underscores, and hyphens")
    return session_id


class SessionMetadataStore:
    def __init__(
        self,
        root: str | Path,
        *,
        session_id: str = "default",
        model: str = "",
    ):
        self.root = Path(root)
        self.session_id = validate_session_id(session_id)
        self.model = model
        self.session_dir = self.root / ".sessions" / session_id
        self.path = self.session_dir / "metadata.json"

    def load_or_create(self) -> SessionMetadata:
        if self.path.exists():
            return self._read()

        now = utc_now()
        metadata = SessionMetadata(
            session_id=self.session_id,
            created_at=now,
            updated_at=now,
            cwd=str(self.root),
            model=self.model,
            transcript_path=str((self.session_dir / "transcript.jsonl").relative_to(self.root)),
            summary_path=str((self.session_dir / "summary.md").relative_to(self.root)),
            artifacts_dir=str((self.session_dir / "artifacts").relative_to(self.root)),
        )
        self.write(metadata)
        return metadata

    def write(self, metadata: SessionMetadata) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(metadata), ensure_ascii=False, indent=METADATA_JSON_INDENT, sort_keys=True),
            encoding="utf-8",
        )

    def update_counts(
        self,
        *,
        event_count: int,
        message_count: int,
        summary_status: str | None = None,
        summary_attempts: int | None = None,
        last_restore_mode: str | None = None,
        summary_error: str | None = None,
        compacted_until_event_id: int | None = None,
    ) -> SessionMetadata:
        metadata = self.load_or_create()
        updated = SessionMetadata(
            **{
                **asdict(metadata),
                "updated_at": utc_now(),
                "event_count": event_count,
                "message_count": message_count,
                "summary_status": summary_status if summary_status is not None else metadata.summary_status,
                "summary_attempts": (
                    summary_attempts if summary_attempts is not None else metadata.summary_attempts
                ),
                "last_restore_mode": (
                    last_restore_mode if last_restore_mode is not None else metadata.last_restore_mode
                ),
                "summary_error": summary_error,
                "compacted_until_event_id": (
                    compacted_until_event_id
                    if compacted_until_event_id is not None
                    else metadata.compacted_until_event_id
                ),
            }
        )
        self.write(updated)
        return updated

    def list_sessions(self) -> list[SessionMetadata]:
        sessions_root = self.root / ".sessions"
        if not sessions_root.exists():
            return []
        sessions: list[SessionMetadata] = []
        for metadata_path in sessions_root.glob("*/metadata.json"):
            try:
                sessions.append(self._read_path(metadata_path))
            except Exception:
                continue
        return sorted(sessions, key=lambda metadata: metadata.updated_at, reverse=True)

    def rename_session(self, title: str) -> SessionMetadata:
        normalized_title = _normalize_title(title)
        metadata = self.load_or_create()
        updated = SessionMetadata(
            **{
                **asdict(metadata),
                "title": normalized_title,
                "title_source": "user",
                "updated_at": utc_now(),
            }
        )
        self.write(updated)
        return updated

    def update_after_user_message(
        self,
        message: str,
        *,
        event_count: int,
        message_count: int,
    ) -> SessionMetadata:
        metadata = self.load_or_create()
        normalized_message = " ".join(message.strip().split())
        title = metadata.title
        title_source = metadata.title_source
        if title_source == "auto" and metadata.last_user_message is None:
            title = _title_from_message(normalized_message)
        updated = SessionMetadata(
            **{
                **asdict(metadata),
                "title": title,
                "title_source": title_source,
                "last_user_message": normalized_message or None,
                "updated_at": utc_now(),
                "event_count": event_count,
                "message_count": message_count,
            }
        )
        self.write(updated)
        return updated

    def _read(self) -> SessionMetadata:
        return self._read_path(self.path)

    def _read_path(self, path: Path) -> SessionMetadata:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("title", DEFAULT_SESSION_TITLE)
        payload.setdefault("title_source", "auto")
        payload.setdefault("last_user_message", None)
        if payload["title_source"] not in VALID_TITLE_SOURCES:
            payload["title_source"] = "auto"
        return SessionMetadata(**payload)


def _normalize_title(title: str) -> str:
    normalized = " ".join(title.strip().split())
    if not normalized:
        raise ValueError("title must be a non-empty string")
    return normalized[:TITLE_MAX_CHARS]


def _title_from_message(message: str) -> str:
    if not message:
        return DEFAULT_SESSION_TITLE
    return message[:TITLE_PREVIEW_CHARS]
