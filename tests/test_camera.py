import subprocess
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
import server


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_capture_returns_uncached_jpeg(self):
        photo = Image.new("RGB", (80, 40), "blue")
        photo.paste("red", (0, 0, 40, 40))
        buffer = BytesIO()
        photo.save(buffer, format="JPEG")
        jpeg = buffer.getvalue()
        with patch("server.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, jpeg, b"")
            response = self.client.post("/capture")
        self.assertEqual(response.status_code, 200)
        with Image.open(BytesIO(response.data)) as upright:
            self.assertEqual(upright.size, (40, 80))
            # 左红右蓝逆时针旋转后应为上蓝下红。
            top = upright.getpixel((20, 20))
            bottom = upright.getpixel((20, 60))
            self.assertGreater(top[2], 200)
            self.assertLess(top[0], 50)
            self.assertGreater(bottom[0], 200)
            self.assertLess(bottom[2], 50)
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
