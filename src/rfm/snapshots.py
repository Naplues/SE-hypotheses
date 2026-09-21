"""Download and extract exact GitHub commit snapshots for SWE-bench tasks."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import posixpath
import re
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from rfm.io import dump_json, read_jsonl

DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class SnapshotSpec:
    instance_id: str
    repo: str
    base_commit: str


@dataclass(frozen=True)
class PreparedSnapshot:
    path: Path
    manifest_path: Path
    archive_path: Path
    archive_sha256: str
    source_tree_sha256: str


def load_snapshot_spec(input_path: str | Path, instance_id: str) -> SnapshotSpec:
    """Resolve one SWE-bench task without loading unrelated task fields."""

    for spec in load_snapshot_specs(input_path):
        if spec.instance_id == instance_id:
            return spec
    raise ValueError(f"Unknown instance_id: {instance_id}")


def load_snapshot_specs(input_path: str | Path) -> list[SnapshotSpec]:
    """Load and validate every snapshot identity in dataset order."""

    specs: list[SnapshotSpec] = []
    seen: set[str] = set()
    for record in read_jsonl(input_path):
        instance_id = str(record.get("instance_id", "")).strip()
        repo = str(record.get("repo", "")).strip()
        commit = str(record.get("base_commit", "")).strip()
        if not instance_id:
            raise ValueError("SWE-bench record is missing instance_id")
        if instance_id in seen:
            raise ValueError(f"Duplicate instance_id: {instance_id}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError(f"Invalid GitHub repository for {instance_id}: {repo!r}")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
            raise ValueError(f"Invalid base_commit for {instance_id}: {commit!r}")
        seen.add(instance_id)
        specs.append(SnapshotSpec(instance_id=instance_id, repo=repo, base_commit=commit.lower()))
    if not specs:
        raise ValueError(f"No SWE-bench tasks found in {input_path}")
    return specs


def download_commit_snapshot(
    spec: SnapshotSpec,
    cache_dir: str | Path,
    output_root: str | Path,
    *,
    force: bool = False,
    archive_url: str | None = None,
) -> dict[str, Any]:
    """Download, validate, and atomically extract one GitHub commit archive."""

    cache_root = Path(cache_dir).resolve()
    snapshot_root = Path(output_root).resolve()
    slug = _safe_slug(spec.instance_id)
    repo_slug = _safe_slug(spec.repo)
    archive = cache_root / f"{repo_slug}-{spec.base_commit}.tar.gz"
    output = snapshot_root / slug
    manifest_path = snapshot_root / ".metadata" / f"{slug}.json"
    url = archive_url or (f"https://codeload.github.com/{spec.repo}/tar.gz/{spec.base_commit}")

    if output.exists() and not force:
        if not manifest_path.is_file():
            raise ValueError(f"Snapshot exists without metadata: {output}")
        return {
            "status": "skipped",
            "instance_id": spec.instance_id,
            "repo": spec.repo,
            "base_commit": spec.base_commit,
            "snapshot_dir": str(output),
            "manifest": str(manifest_path),
        }

    cache_root.mkdir(parents=True, exist_ok=True)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    if force:
        archive.unlink(missing_ok=True)
    if not archive.exists():
        _download_archive(url, archive)
    _archive_root(archive)

    temporary = Path(tempfile.mkdtemp(prefix=f".{slug}-", dir=snapshot_root))
    try:
        _extract_archive(archive, temporary)
        if not any(temporary.iterdir()):
            raise ValueError(f"Archive contains no source files: {archive}")
        if output.exists():
            shutil.rmtree(output)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    manifest = {
        "schema_version": 1,
        "instance_id": spec.instance_id,
        "repo": spec.repo,
        "base_commit": spec.base_commit,
        "archive_url": url,
        "archive_path": str(archive),
        "archive_sha256": file_sha256(archive),
        "snapshot_dir": str(output),
    }
    dump_json(manifest_path, manifest)
    return {"status": "completed", **manifest, "manifest": str(manifest_path)}


def validate_commit_snapshot(spec: SnapshotSpec, output_root: str | Path) -> PreparedSnapshot:
    """Validate a downloaded snapshot and return immutable provenance."""

    snapshot_root = Path(output_root).resolve()
    slug = _safe_slug(spec.instance_id)
    snapshot = snapshot_root / slug
    manifest_path = snapshot_root / ".metadata" / f"{slug}.json"
    if not snapshot.is_dir():
        raise ValueError(
            f"Snapshot is missing for {spec.instance_id}; run "
            f"download_commit_archive.py --instance-id {spec.instance_id}"
        )
    if not manifest_path.is_file():
        raise ValueError(f"Snapshot metadata is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid snapshot metadata {manifest_path}: {exc}") from exc
    expected = {
        "instance_id": spec.instance_id,
        "repo": spec.repo,
        "base_commit": spec.base_commit,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(
                f"Snapshot metadata mismatch for {field}: "
                f"expected {value!r}, found {manifest.get(field)!r}"
            )
    archive_path = Path(str(manifest.get("archive_path", "")))
    recorded_archive_hash = str(manifest.get("archive_sha256", ""))
    if not archive_path.is_file():
        raise ValueError(f"Snapshot archive is missing: {archive_path}")
    actual_archive_hash = file_sha256(archive_path)
    if actual_archive_hash != recorded_archive_hash:
        raise ValueError(f"Snapshot archive SHA-256 mismatch: {archive_path}")
    return PreparedSnapshot(
        path=snapshot,
        manifest_path=manifest_path,
        archive_path=archive_path,
        archive_sha256=actual_archive_hash,
        source_tree_sha256=source_tree_sha256(snapshot),
    )


def source_tree_sha256(root: str | Path) -> str:
    """Hash paths, file modes, file contents, and symlink targets deterministically."""

    source = Path(root).resolve()
    if not source.is_dir():
        raise ValueError(f"Source tree is not a directory: {source}")
    digest = hashlib.sha256()
    paths = sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix())
    for path in paths:
        relative = path.relative_to(source).as_posix().encode()
        mode = f"{path.lstat().st_mode & 0o777:o}".encode()
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + mode + b"\0")
            digest.update(os.readlink(path).encode())
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0" + mode + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0" + mode + b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        else:
            raise ValueError(f"Unsupported source tree entry: {path}")
        digest.update(b"\0")
    return digest.hexdigest()


def _download_archive(url: str, target: Path) -> None:
    partial = target.with_suffix(target.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            existing = partial.stat().st_size if partial.exists() else 0
            headers = {"User-Agent": "rfm-experiments/0.2"}
            if existing:
                headers["Range"] = f"bytes={existing}-"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", None)
                append = existing > 0 and status == 206
                with partial.open("ab" if append else "wb") as handle:
                    shutil.copyfileobj(response, handle)
            _archive_root(partial)
            partial.replace(target)
            return
        except (
            OSError,
            TimeoutError,
            tarfile.TarError,
            http.client.HTTPException,
            urllib.error.URLError,
        ) as exc:
            last_error = exc
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(2 ** (attempt - 1))
    raise ValueError(f"Archive download failed after {DOWNLOAD_ATTEMPTS} attempts: {last_error}")


def _archive_root(archive: Path) -> str:
    with tarfile.open(archive, "r:gz") as handle:
        roots = {
            PurePosixPath(member.name).parts[0]
            for member in handle.getmembers()
            if PurePosixPath(member.name).parts
        }
    if len(roots) != 1:
        raise ValueError(f"Archive must contain exactly one top-level directory: {archive}")
    return next(iter(roots))


def _extract_archive(archive: Path, target: Path) -> None:
    root = _archive_root(archive)
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle.getmembers():
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != root or len(parts) == 1:
                continue
            relative = PurePosixPath(*parts[1:])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe archive path: {member.name}")
            destination = target.joinpath(*relative.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if member.isfile():
                source = handle.extractfile(member)
                if source is None:
                    raise ValueError(f"Cannot read archive member: {member.name}")
                with source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                os.chmod(destination, member.mode & 0o777)
                continue
            if member.issym():
                if PurePosixPath(member.linkname).is_absolute():
                    raise ValueError(f"Unsafe archive symlink: {member.name}")
                normalized = posixpath.normpath(str(relative.parent / member.linkname))
                if normalized == ".." or normalized.startswith("../"):
                    raise ValueError(f"Unsafe archive symlink: {member.name}")
                destination.symlink_to(member.linkname)
                continue
            raise ValueError(f"Unsupported archive member: {member.name}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not slug:
        raise ValueError(f"Cannot create a path from {value!r}")
    return slug
