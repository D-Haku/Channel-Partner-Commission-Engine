"""Storage Uploader module for the Channel Partner Commission Engine.

Uploads generated report files to configured storage backends.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the interface for storage backends."""

    def upload(self, local_path: Path, remote_key: str) -> str:
        """Upload a local file to the storage backend.

        Args:
            local_path: Path to the local file to upload.
            remote_key: The key/path to use in the remote storage.

        Returns:
            The full storage location string of the uploaded file.

        Raises:
            OSError: If the upload fails.
        """
        ...


class LocalFSBackend:
    """Local filesystem storage backend.

    Copies files to a configured base directory, simulating
    object storage uploads for local development.
    """

    def __init__(self, base_path: Path) -> None:
        """Initialize LocalFSBackend.

        Args:
            base_path: Target directory for uploaded files.
        """
        self.base_path = base_path

    def upload(self, local_path: Path, remote_key: str) -> str:
        """Copy a file to the base_path under the given remote_key.

        Args:
            local_path: Path to the local file to upload.
            remote_key: The filename/key to use in the target directory.

        Returns:
            The full path to the copied file as a string.

        Raises:
            OSError: If the copy operation fails.
        """
        self.base_path.mkdir(parents=True, exist_ok=True)
        destination = self.base_path / remote_key
        # Create parent directories for nested keys
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        return str(destination)


class StorageUploader:
    """Uploads report files using a configured storage backend.

    On upload failure, the local file is retained and the error is reported.
    """

    def __init__(self, backend: StorageBackend) -> None:
        """Initialize StorageUploader.

        Args:
            backend: A storage backend implementing the StorageBackend protocol.
        """
        self.backend = backend

    def upload_reports(self, paths: list[Path]) -> list[str]:
        """Upload a list of report files to the storage backend.

        For each path, uploads using the filename as the remote key.
        On failure for any individual file, retains the local file and
        raises the exception (does not delete the source).

        Args:
            paths: List of local file paths to upload.

        Returns:
            List of storage location strings for successfully uploaded files.

        Raises:
            OSError: If any upload fails. Local files are always retained.
        """
        locations: list[str] = []
        for path in paths:
            remote_key = path.name
            location = self.backend.upload(path, remote_key)
            locations.append(location)
        return locations
