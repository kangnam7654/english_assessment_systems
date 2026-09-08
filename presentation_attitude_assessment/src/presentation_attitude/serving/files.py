"""Local analysis workspace, independent of the job metadata database."""

import hashlib
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class EmptyUpload(ValueError):
    """An upload contains no video bytes."""


class UploadTooLarge(ValueError):
    """An upload exceeds the configured file size limit."""


@dataclass(frozen=True)
class UploadedVideo:
    sha256: str
    size_bytes: int


class LocalJobFiles:
    def __init__(self, directory):
        self.directory = Path(directory).resolve() / "jobs"
        self.directory.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id):
        # IDs originate from server UUIDs, never client filenames.
        return self.directory / job_id

    @contextmanager
    def stage_upload(
        self, job_id: str, source: BinaryIO, *, max_bytes: int
    ) -> Iterator[UploadedVideo]:
        """Save before publishing a job; roll back files if publication fails.

        The caller owns the input stream and must create the repository entry
        inside this context. An existing job directory is never overwritten.
        """
        directory = self.job_dir(job_id)
        directory.mkdir()
        digest, size = hashlib.sha256(), 0
        try:
            with (directory / "upload.partial").open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLarge("Video exceeds file size limit")
                    digest.update(chunk)
                    target.write(chunk)
            if size == 0:
                raise EmptyUpload("Video is empty")
            (directory / "upload.partial").replace(directory / "source.video")
            yield UploadedVideo(sha256=digest.hexdigest(), size_bytes=size)
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
