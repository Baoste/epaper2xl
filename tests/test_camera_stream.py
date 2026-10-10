from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import queue
import threading
import unittest
from unittest.mock import Mock, patch

from camera_stream import CameraError, PersistentCamera, jpeg_frames


class FeedPipe:
    def __init__(self):
        self.queue = queue.Queue()

    def read(self, size):
        return self.queue.get(timeout=3)

    def close(self):
        self.queue.put(b"")


class CameraStreamTests(unittest.TestCase):
    def test_split_markers_junk_and_multiple_frames(self):
        stream = Mock()
        stream.read.side_effect = [b"junk\xff", b"\xd8one\xff", b"\xd9\xff\xd8two\xff\xd9", b""]
        self.assertEqual(list(jpeg_frames(stream)), [b"\xff\xd8one\xff\xd9", b"\xff\xd8two\xff\xd9"])

    def test_corrupt_stream_has_bounded_buffer(self):
        with self.assertRaises(CameraError):
            list(jpeg_frames(BytesIO(b"\xff\xd8" + b"x" * (2 * 1024 * 1024))))

    def make_camera(self):
        camera = PersistentCamera()
        process = Mock()
        process.stdout = FeedPipe()
        process.poll.return_value = None

        def terminate():
            process.poll.return_value = 0
            process.stdout.close()

        process.terminate.side_effect = terminate
        patcher = patch("camera_stream.subprocess.Popen", return_value=process)
        spawn = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(camera.close)
        camera._start()
        camera._ready_after = 0
        return camera, process, spawn

    def test_reuses_process_and_requires_fresh_frames(self):
        camera, process, spawn = self.make_camera()
        with ThreadPoolExecutor(max_workers=1) as executor:
            for payload in (b"first", b"second"):
                waiting = threading.Event()
                original_wait = camera._condition.wait

                def wait(seconds):
                    waiting.set()
                    return original_wait(seconds)

                with patch.object(camera._condition, "wait", side_effect=wait):
                    future = executor.submit(camera.capture, 2)
                    self.assertTrue(waiting.wait(1))
                    self.assertFalse(future.done())
                    frame = b"\xff\xd8" + payload + b"\xff\xd9"
                    process.stdout.queue.put(frame)
                    self.assertEqual(future.result(timeout=2), frame)
        spawn.assert_called_once()
        camera.close()
        process.terminate.assert_called_once()

    def test_timeout_releases_process(self):
        camera, process, _ = self.make_camera()
        with self.assertRaises(TimeoutError):
            camera.capture(timeout=0)
        process.terminate.assert_called_once()
        self.assertIsNone(camera._process)

    def test_close_wakes_capture_and_prevents_reopening(self):
        camera, _, spawn = self.make_camera()
        waiting = threading.Event()
        original_wait = camera._condition.wait

        def wait(seconds):
            waiting.set()
            return original_wait(seconds)

        with ThreadPoolExecutor(max_workers=1) as executor, patch.object(camera._condition, "wait", side_effect=wait):
            future = executor.submit(camera.capture, 2)
            self.assertTrue(waiting.wait(1))
            camera.close()
            with self.assertRaises(CameraError):
                future.result(timeout=2)
        with self.assertRaises(CameraError):
            camera.capture()
        spawn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
