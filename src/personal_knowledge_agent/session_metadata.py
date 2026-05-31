from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .schemas import SessionMetadata


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SessionMetadataStore:
    def __init__(
        self,
        root: str | Path,
        *,
        session_id: str = "default",
        model: str = "",
    ):
        self.root = Path(root)
        self.session_id = session_id
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
            json.dumps(asdict(metadata), ensure_ascii=False, indent=2, sort_keys=True),
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

    def _read(self) -> SessionMetadata:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return SessionMetadata(**payload)
