"""Unit tests for the StorageUploader module."""

from pathlib import Path

import pytest

from commission_engine.uploader import LocalFSBackend, StorageBackend, StorageUploader


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample report files."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "payout_report.csv").write_text("LAN,Amount\nLAN001,1000\n")
    (src / "contest_report.csv").write_text("Partner_ID,Payout\nP001,5000\n")
    return src


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for uploaded files."""
    return tmp_path / "uploads"


class TestLocalFSBackend:
    """Tests for LocalFSBackend."""

    def test_implements_storage_backend_protocol(self, upload_dir: Path):
        """LocalFSBackend satisfies the StorageBackend protocol."""
        backend = LocalFSBackend(upload_dir)
        assert isinstance(backend, StorageBackend)

    def test_upload_creates_target_directory(self, source_dir: Path, upload_dir: Path):
        """Upload creates the base_path directory if it does not exist."""
        backend = LocalFSBackend(upload_dir)
        assert not upload_dir.exists()
        source_file = source_dir / "payout_report.csv"
        backend.upload(source_file, "payout_report.csv")
        assert upload_dir.exists()

    def test_upload_copies_file(self, source_dir: Path, upload_dir: Path):
        """Upload copies the file content to the target location."""
        backend = LocalFSBackend(upload_dir)
        source_file = source_dir / "payout_report.csv"
        backend.upload(source_file, "payout_report.csv")
        target = upload_dir / "payout_report.csv"
        assert target.exists()
        assert target.read_text() == source_file.read_text()

    def test_upload_returns_full_path(self, source_dir: Path, upload_dir: Path):
        """Upload returns the full path to the copied file as a string."""
        backend = LocalFSBackend(upload_dir)
        source_file = source_dir / "payout_report.csv"
        result = backend.upload(source_file, "payout_report.csv")
        assert result == str(upload_dir / "payout_report.csv")

    def test_upload_with_nested_key(self, source_dir: Path, upload_dir: Path):
        """Upload supports nested remote keys with subdirectories."""
        backend = LocalFSBackend(upload_dir)
        source_file = source_dir / "payout_report.csv"
        result = backend.upload(source_file, "2024/01/payout_report.csv")
        expected = upload_dir / "2024" / "01" / "payout_report.csv"
        assert result == str(expected)
        assert expected.exists()

    def test_upload_does_not_delete_source(self, source_dir: Path, upload_dir: Path):
        """Upload never deletes the source file."""
        backend = LocalFSBackend(upload_dir)
        source_file = source_dir / "payout_report.csv"
        backend.upload(source_file, "payout_report.csv")
        assert source_file.exists()

    def test_upload_failure_does_not_delete_source(self, source_dir: Path, tmp_path: Path):
        """On upload failure, the source file is retained."""
        # Point to a path where we cannot write (use a file as the base_path)
        blocker = tmp_path / "blocker_file"
        blocker.write_text("I am a file, not a directory")
        backend = LocalFSBackend(blocker / "subdir")
        source_file = source_dir / "payout_report.csv"
        with pytest.raises(OSError):
            backend.upload(source_file, "payout_report.csv")
        # Source file must still exist
        assert source_file.exists()


class TestStorageUploader:
    """Tests for StorageUploader."""

    def test_upload_reports_returns_locations(self, source_dir: Path, upload_dir: Path):
        """upload_reports returns a list of storage location strings."""
        backend = LocalFSBackend(upload_dir)
        uploader = StorageUploader(backend)
        paths = [
            source_dir / "payout_report.csv",
            source_dir / "contest_report.csv",
        ]
        locations = uploader.upload_reports(paths)
        assert len(locations) == 2
        assert str(upload_dir / "payout_report.csv") in locations
        assert str(upload_dir / "contest_report.csv") in locations

    def test_upload_reports_empty_list(self, upload_dir: Path):
        """upload_reports with no paths returns an empty list."""
        backend = LocalFSBackend(upload_dir)
        uploader = StorageUploader(backend)
        locations = uploader.upload_reports([])
        assert locations == []

    def test_upload_reports_uses_filename_as_key(self, source_dir: Path, upload_dir: Path):
        """upload_reports uses the filename as the remote key."""
        backend = LocalFSBackend(upload_dir)
        uploader = StorageUploader(backend)
        paths = [source_dir / "payout_report.csv"]
        uploader.upload_reports(paths)
        assert (upload_dir / "payout_report.csv").exists()

    def test_upload_reports_failure_retains_local_files(
        self, source_dir: Path, tmp_path: Path
    ):
        """On failure, local files are retained and error is raised."""
        blocker = tmp_path / "blocker_file"
        blocker.write_text("I am a file, not a directory")
        backend = LocalFSBackend(blocker / "subdir")
        uploader = StorageUploader(backend)
        paths = [source_dir / "payout_report.csv"]
        with pytest.raises(OSError):
            uploader.upload_reports(paths)
        # Source file still intact
        assert (source_dir / "payout_report.csv").exists()
