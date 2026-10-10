import json
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
import server


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        comparison = patch("server.compare_photo", return_value={
            "status": "ok", "similarity": 0.7654, "elapsed_ms": 120,
        })
        self.compare = comparison.start()
        self.addCleanup(comparison.stop)

    def test_capture_returns_uncached_jpeg(self):
        photo = Image.new("RGB", (80, 40), "blue")
        photo.paste("red", (0, 0, 40, 40))
        photo.paste("lime", (40, 0, 80, 20))
        buffer = BytesIO()
        photo.save(buffer, format="JPEG")
        jpeg = buffer.getvalue()
        with patch.object(server.camera, "capture", return_value=jpeg) as capture:
            response = self.client.post("/capture")
        self.assertEqual(response.status_code, 200)
        with Image.open(BytesIO(response.data)) as upright:
            self.assertEqual(upright.size, (40, 80))
            # 旋转后再左右镜像：右下蓝变为左上，右上绿变为右上。
            top = upright.getpixel((10, 20))
            top_right = upright.getpixel((30, 20))
            bottom = upright.getpixel((20, 60))
            self.assertGreater(top[2], 200)
            self.assertLess(top[0], 50)
            self.assertGreater(top_right[1], 200)
            self.assertLess(top_right[2], 50)
            self.assertGreater(bottom[0], 200)
            self.assertLess(bottom[2], 50)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(response.headers["X-Face-Result"])["similarity"], 0.7654)
        self.compare.assert_called_once_with(response.data)
        capture.assert_called_once()
        self.assertFalse(server.camera_lock.locked())

    def test_comparison_unavailable_still_returns_photo(self):
        self.compare.return_value = {"status": "unavailable", "message": "缺少模型"}
        buffer = BytesIO()
        Image.new("RGB", (64, 48)).save(buffer, format="JPEG")
        with patch.object(server.camera, "capture", return_value=buffer.getvalue()):
            response = self.client.post("/capture")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(json.loads(response.headers["X-Face-Result"]), self.compare.return_value)

    def test_busy_camera_does_not_launch_another_process(self):
        with server.camera_lock, patch.object(server.camera, "capture") as capture:
            response = self.client.post("/capture")
            self.assertEqual(response.status_code, 409)
            capture.assert_not_called()

    def test_failures_release_camera_for_next_request(self):
        failures = [
            (FileNotFoundError(), 503),
            (TimeoutError(), 504),
            (server.CameraError("interrupted"), 503),
            (PermissionError(), 503),
        ]
        for error, status in failures:
            with self.subTest(error=type(error).__name__):
                with patch.object(server.camera, "capture", side_effect=error):
                    response = self.client.post("/capture")
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json["status"], "error")
                self.assertFalse(server.camera_lock.locked())

    def test_invalid_output_is_rejected(self):
        with patch.object(server.camera, "capture", return_value=b""):
            response = self.client.post("/capture")
        self.assertEqual(response.status_code, 502)
        self.assertFalse(server.camera_lock.locked())

    def test_get_does_not_trigger_capture(self):
        with patch.object(server.camera, "capture") as capture:
            self.client.get("/capture")
            capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
