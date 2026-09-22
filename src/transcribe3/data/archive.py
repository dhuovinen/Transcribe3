from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path

from transcribe3.data.session import SessionRepository
from transcribe3.shared.types import TranscriptSession


class ArchiveError(Exception):
    """Base exception for safe external recording storage operations."""


class ArchiveConfigurationError(ArchiveError):
    """Raised when no usable archive location has been configured."""


class ArchiveConflictError(ArchiveError):
    """Raised instead of overwriting a recording with different contents."""


class ArchiveRepository:
    """Moves verified audio copies between a local session and an archive root."""

    _RECORDINGS_DIR = "recordings"
    _COPY_CHUNK_SIZE = 1024 * 1024

    @staticmethod
    def configure_root(archive_dir: str, sessions_dir: Path) -> Path:
        value = archive_dir.strip()
        if not value:
            raise ArchiveConfigurationError("Choose an archive folder first.")

        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ArchiveConfigurationError("Archive folder must be an absolute path.")
        root = path.resolve()
        if root == Path(root.anchor):
            raise ArchiveConfigurationError("Choose a folder inside the archive drive, not the drive root.")

        local_root = sessions_dir.resolve()
        if ArchiveRepository._paths_overlap(root, local_root):
            raise ArchiveConfigurationError("Archive folder must be separate from the local sessions folder.")

        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ArchiveConfigurationError(f"Could not create archive folder: {exc}") from exc
        if not root.is_dir():
            raise ArchiveConfigurationError("The archive path is not a directory.")
        return root

    @staticmethod
    def archive(
        session: TranscriptSession,
        sessions_dir: Path,
        archive_root: str | None,
        remove_local: bool,
    ) -> TranscriptSession:
        root = ArchiveRepository._usable_root(archive_root)
        local_path = ArchiveRepository.local_audio_path(session, sessions_dir)
        if local_path is None or not local_path.is_file():
            raise ArchiveError("The local recording is not available to archive.")

        destination = ArchiveRepository.archive_path(session, root)
        ArchiveRepository._copy_if_needed(local_path, destination)

        updated = session.model_copy(
            update={
                "archived_audio_path": destination.relative_to(root).as_posix(),
                "archived_at": datetime.utcnow(),
            }
        )
        SessionRepository.save(updated, sessions_dir)

        if remove_local:
            try:
                local_path.unlink()
            except OSError as exc:
                raise ArchiveError(
                    f"Recording was safely archived, but the local copy could not be removed: {exc}"
                ) from exc
        return updated

    @staticmethod
    def restore(
        session: TranscriptSession,
        sessions_dir: Path,
        archive_root: str | None,
    ) -> TranscriptSession:
        root = ArchiveRepository._usable_root(archive_root)
        source = ArchiveRepository.configured_archive_path(session, root)
        if source is None or not source.is_file():
            raise ArchiveError("The archived recording is not available. Connect the archive drive and try again.")

        destination = ArchiveRepository.local_audio_path(session, sessions_dir)
        if destination is None:
            raise ArchiveError("This session does not have an audio recording to restore.")
        ArchiveRepository._copy_if_needed(source, destination)
        return session

    @staticmethod
    def delete_local_copy(
        session: TranscriptSession,
        sessions_dir: Path,
        archive_root: str | None,
    ) -> TranscriptSession:
        root = ArchiveRepository._usable_root(archive_root)
        local_path = ArchiveRepository.local_audio_path(session, sessions_dir)
        archive_path = ArchiveRepository.configured_archive_path(session, root)
        if local_path is None or not local_path.exists():
            raise ArchiveError("There is no local recording to remove.")
        if archive_path is None or not archive_path.is_file():
            raise ArchiveError("Local deletion is blocked until a verified archive copy is available.")
        if not ArchiveRepository._files_match(local_path, archive_path):
            raise ArchiveConflictError(
                "Local and archived recordings differ, so the local copy was not removed."
            )
        try:
            local_path.unlink()
        except OSError as exc:
            raise ArchiveError(f"Could not remove local recording: {exc}") from exc
        return session

    @staticmethod
    def local_audio_path(session: TranscriptSession, sessions_dir: Path) -> Path | None:
        if not session.audio_file:
            return None
        filename = ArchiveRepository._safe_filename(session.audio_file)
        session_dir = (sessions_dir / session.session_id).resolve()
        path = (session_dir / filename).resolve()
        if not ArchiveRepository._is_within(path, session_dir):
            raise ArchiveError("Invalid local recording path.")
        return path

    @staticmethod
    def archive_path(session: TranscriptSession, archive_root: Path) -> Path:
        filename = ArchiveRepository._safe_filename(session.audio_file)
        destination = (archive_root / ArchiveRepository._RECORDINGS_DIR / session.session_id / filename).resolve()
        if not ArchiveRepository._is_within(destination, archive_root):
            raise ArchiveError("Invalid archive recording path.")
        return destination

    @staticmethod
    def configured_archive_path(session: TranscriptSession, archive_root: Path) -> Path | None:
        if not session.archived_audio_path:
            return None
        relative = Path(session.archived_audio_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ArchiveError("Invalid archived recording path.")
        path = (archive_root / relative).resolve()
        if not ArchiveRepository._is_within(path, archive_root):
            raise ArchiveError("Invalid archived recording path.")
        return path

    @staticmethod
    def _usable_root(archive_root: str | None) -> Path:
        if not archive_root:
            raise ArchiveConfigurationError("Configure an archive folder before managing recordings.")
        root = Path(archive_root).expanduser().resolve()
        if not root.is_dir():
            raise ArchiveConfigurationError(
                "Archive folder is unavailable. Connect the archive drive and try again."
            )
        return root

    @staticmethod
    def _safe_filename(filename: str | None) -> str:
        if not filename:
            raise ArchiveError("This session does not have an audio recording.")
        path = Path(filename)
        if path.name != filename or path.is_absolute() or filename in {".", ".."}:
            raise ArchiveError("Invalid recording filename.")
        return filename

    @staticmethod
    def _copy_if_needed(source: Path, destination: Path) -> None:
        if destination.exists():
            if ArchiveRepository._files_match(source, destination):
                return
            raise ArchiveConflictError(
                "A different recording already exists at the archive destination; nothing was overwritten."
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
        try:
            ArchiveRepository._copy_with_digest(source, temporary)
            if not ArchiveRepository._files_match(source, temporary):
                raise ArchiveError("Archive verification failed; the local recording was kept.")
            temporary.replace(destination)
        except OSError as exc:
            raise ArchiveError(f"Could not copy recording: {exc}") from exc
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _copy_with_digest(source: Path, destination: Path) -> str:
        digest = hashlib.sha256()
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            while chunk := input_file.read(ArchiveRepository._COPY_CHUNK_SIZE):
                digest.update(chunk)
                output_file.write(chunk)
            output_file.flush()
            os.fsync(output_file.fileno())
        return digest.hexdigest()

    @staticmethod
    def _files_match(first: Path, second: Path) -> bool:
        if first.stat().st_size != second.stat().st_size:
            return False
        return ArchiveRepository._digest(first) == ArchiveRepository._digest(second)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(ArchiveRepository._COPY_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    @staticmethod
    def _paths_overlap(first: Path, second: Path) -> bool:
        return ArchiveRepository._is_within(first, second) or ArchiveRepository._is_within(second, first)
