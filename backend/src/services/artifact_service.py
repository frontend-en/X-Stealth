"""Safe artifact listing and lookup."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.api.schemas import Artifact, ArtifactType
from src.config import Settings


class ArtifactService:
    """Expose allowlisted runtime artifacts without arbitrary file access."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._roots: dict[ArtifactType, Path] = {
            "log": settings.logs_dir,
            "screenshot": settings.screenshots_dir,
            "trace": settings.traces_dir,
        }
        self._patterns: dict[ArtifactType, tuple[str, ...]] = {
            "log": ("*.log",),
            "screenshot": ("*.png", "*.jpg", "*.jpeg"),
            "trace": ("*.zip",),
        }

    def list_artifacts(self, artifact_type: ArtifactType | None = None, limit: int = 50) -> list[Artifact]:
        types = [artifact_type] if artifact_type else list(self._roots)
        artifacts: list[Artifact] = []
        for current_type in types:
            root = self._roots[current_type]
            for path in self._iter_files(root, self._patterns[current_type]):
                stat = path.stat()
                artifact_id = self._make_id(current_type, path)
                artifacts.append(
                    Artifact(
                        id=artifact_id,
                        type=current_type,
                        name=path.name,
                        sizeBytes=stat.st_size,
                        createdAt=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        downloadUrl=f"/api/v1/artifacts/{artifact_id}/download",
                    )
                )
        artifacts.sort(key=lambda item: item.createdAt or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return artifacts[:limit]

    def resolve_artifact_path(self, artifact_id: str) -> Path | None:
        for artifact_type in self._roots:
            prefix = f"{artifact_type}-"
            if not artifact_id.startswith(prefix):
                continue
            encoded_name = artifact_id.removeprefix(prefix)
            name = encoded_name.replace("__", ".")
            root = self._roots[artifact_type].resolve()
            candidate = (root / name).resolve()
            if root == candidate.parent and candidate.exists() and candidate.is_file():
                if any(candidate.match(pattern) for pattern in self._patterns[artifact_type]):
                    return candidate
        return None

    def _iter_files(self, root: Path, patterns: tuple[str, ...]) -> list[Path]:
        if not root.exists():
            return []
        files: list[Path] = []
        for pattern in patterns:
            files.extend(path for path in root.glob(pattern) if path.is_file())
        return files

    @staticmethod
    def _make_id(artifact_type: ArtifactType, path: Path) -> str:
        return f"{artifact_type}-{path.name.replace('.', '__')}"
