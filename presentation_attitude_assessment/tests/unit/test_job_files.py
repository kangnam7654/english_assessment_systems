import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from presentation_attitude.serving.files import (
    EmptyUpload,
    LocalJobFiles,
    UploadTooLarge,
)


class JobFilesTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.files = LocalJobFiles(Path(directory))

    def test_complete_input_available_before_publication(self):
        payload = b"video" * 300_000  # Cross the streaming chunk boundary.
        source = io.BytesIO(payload)
        with self.files.stage_upload("job", source, max_bytes=len(payload)) as upload:
            self.assertEqual(upload.size_bytes, len(payload))
            self.assertEqual(upload.sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual(
                (self.files.job_dir("job") / "source.video").read_bytes(), payload
            )
            self.assertFalse((self.files.job_dir("job") / "upload.partial").exists())
        self.assertTrue(self.files.job_dir("job").exists())
        self.assertFalse(source.closed)

    def test_invalid_upload_leaves_no_files(self):
        for payload, error in ((b"", EmptyUpload), (b"1234", UploadTooLarge)):
            with self.subTest(payload=payload), self.assertRaises(error):
                with self.files.stage_upload("job", io.BytesIO(payload), max_bytes=3):
                    self.fail("Invalid input must not be published")
            self.assertFalse(self.files.job_dir("job").exists())

    def test_read_failure_and_publication_interruption_roll_back(self):
        class BrokenStream(io.BytesIO):
            def read(self, size):
                if self.tell():
                    raise OSError("Upload read failed")
                return super().read(size)

        with self.assertRaises(OSError):
            with self.files.stage_upload("job", BrokenStream(b"x"), max_bytes=3):
                self.fail("An incomplete read must not be published")
        self.assertFalse(self.files.job_dir("job").exists())

        with self.assertRaises(KeyboardInterrupt):
            with self.files.stage_upload("job", io.BytesIO(b"x"), max_bytes=3):
                raise KeyboardInterrupt
        self.assertFalse(self.files.job_dir("job").exists())

    def test_existing_job_is_preserved(self):
        with self.files.stage_upload("job", io.BytesIO(b"original"), max_bytes=8):
            pass
        with self.assertRaises(FileExistsError):
            with self.files.stage_upload("job", io.BytesIO(b"new"), max_bytes=8):
                self.fail("An existing job must not be overwritten")
        self.assertEqual(
            (self.files.job_dir("job") / "source.video").read_bytes(), b"original"
        )
