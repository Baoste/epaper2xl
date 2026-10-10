import subprocess
import unittest
from unittest.mock import patch

import server


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_capture_returns_uncached_jpeg(self):
        jpeg = b"\xff\xd8\xff\xe0test\xff\xd9"
        with patch("server.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, jpeg, b"")
            response = self.client.post("/capture")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, jpeg)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(run.call_args.args[0][0], "rpicam-still")
        self.assertEqual(run.call_args.kwargs["timeout"], 20)
        self.assertFalse(server.camera_lock.locked())

    def test_busy_camera_does_not_launch_another_process(self):
        with server.camera_lock, patch("server.subprocess.run") as run:
            response = self.client.post("/capture")
            self.assertEqual(response.status_code, 409)
            run.assert_not_called()

    def test_failures_release_camera_for_next_request(self):
        failures = [
            (FileNotFoundError(), 503),
            (subprocess.TimeoutExpired("rpicam-still", 20), 504),
            (subprocess.CalledProcessError(1, "rpicam-still", stderr=b"busy"), 503),
            (PermissionError(), 503),
        ]
        for error, status in failures:
            with self.subTest(error=type(error).__name__):
                with patch("server.subprocess.run", side_effect=error):
                    response = self.client.post("/capture")
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json["status"], "error")
                self.assertFalse(server.camera_lock.locked())

    def test_invalid_output_is_rejected(self):
        with patch("server.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
            response = self.client.post("/capture")
        self.assertEqual(response.status_code, 502)
        self.assertFalse(server.camera_lock.locked())

    def test_get_does_not_trigger_capture(self):
        with patch("server.subprocess.run") as run:
            self.client.get("/capture")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
