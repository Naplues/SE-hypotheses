import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from rfm.snapshots import (
    download_commit_snapshot,
    load_snapshot_spec,
    load_snapshot_specs,
    source_tree_sha256,
    validate_commit_snapshot,
)


def _archive(path: Path, root: str) -> None:
    content = b"def example():\n    return 1\n"
    with tarfile.open(path, "w:gz") as handle:
        member = tarfile.TarInfo(f"{root}/src/example.py")
        member.size = len(content)
        member.mode = 0o644
        handle.addfile(member, io.BytesIO(content))


def test_download_and_extract_snapshot(tmp_path: Path) -> None:
    commit = "a" * 40
    source = tmp_path / "tasks.jsonl"
    source.write_text(
        json.dumps(
            {
                "instance_id": "owner__repo-1",
                "repo": "owner/repo",
                "base_commit": commit,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    archive = tmp_path / "source.tar.gz"
    _archive(archive, f"repo-{commit}")

    spec = load_snapshot_spec(source, "owner__repo-1")
    assert load_snapshot_specs(source) == [spec]
    result = download_commit_snapshot(
        spec,
        tmp_path / "cache",
        tmp_path / "snapshots",
        archive_url=archive.as_uri(),
    )

    snapshot = tmp_path / "snapshots" / "owner__repo-1"
    assert result["status"] == "completed"
    assert (snapshot / "src" / "example.py").read_text(encoding="utf-8").startswith("def")
    cached = next((tmp_path / "cache").glob("*.tar.gz"))
    assert result["archive_sha256"] == hashlib.sha256(cached.read_bytes()).hexdigest()
    prepared = validate_commit_snapshot(spec, tmp_path / "snapshots")
    assert prepared.archive_sha256 == result["archive_sha256"]
    original_tree_hash = prepared.source_tree_sha256
    (snapshot / "src" / "example.py").write_text("changed\n", encoding="utf-8")
    assert source_tree_sha256(snapshot) != original_tree_hash
    assert (
        download_commit_snapshot(
            spec,
            tmp_path / "cache",
            tmp_path / "snapshots",
            archive_url=archive.as_uri(),
        )["status"]
        == "skipped"
    )

    cached.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_commit_snapshot(spec, tmp_path / "snapshots")


def test_all_cli_skips_completed_snapshots(tmp_path: Path) -> None:
    source = tmp_path / "tasks.jsonl"
    records = [
        {
            "instance_id": f"owner__repo-{index}",
            "repo": "owner/repo",
            "base_commit": str(index) * 40,
        }
        for index in (1, 2)
    ]
    source.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    snapshots = tmp_path / "snapshots"
    metadata = snapshots / ".metadata"
    metadata.mkdir(parents=True)
    for record in records:
        (snapshots / record["instance_id"]).mkdir()
        (metadata / f"{record['instance_id']}.json").write_text("{}\n", encoding="utf-8")

    project = Path(__file__).resolve().parents[1]
    process = subprocess.run(
        [
            sys.executable,
            str(project / "scripts" / "download_commit_archive.py"),
            "--all",
            "--input",
            str(source),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output",
            str(snapshots),
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )
    summary = json.loads(process.stdout)
    assert summary["selected"] == 2
    assert summary["completed"] == []
    assert summary["skipped"] == ["owner__repo-1", "owner__repo-2"]
    assert summary["failures"] == []
