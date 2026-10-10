"""One persistent rpicam-vid process; retain only the latest MJPEG frame."""

import logging
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    pass


def jpeg_frames(stream):
    buffer = bytearray()
    while True:
        chunk = stream.read(65536)
        if not chunk:
            return
        buffer.extend(chunk)
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                buffer[:] = buffer[-1:]
                break
            if start:
                del buffer[:start]
            end = buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(buffer) > 2 * 1024 * 1024:
                    raise CameraError("摄像头视频帧异常，等待重新连接")
                break
            frame = bytes(buffer[:end + 2])
            del buffer[:end + 2]
            yield frame


class PersistentCamera:
    """Serialize capture() callers externally; close() can interrupt a capture."""

    def __init__(self):
        self._lifecycle = threading.Lock()
        self._condition = threading.Condition()
        self._process = None
        self._reader = None
        self._closed = False
        self._ended = True
        self._sequence = 0
        self._frame = None
        self._frame_time = 0
        self._ready_after = 0

    def _read(self, process):
        try:
            for frame in jpeg_frames(process.stdout):
                with self._condition:
                    self._frame = frame
                    self._frame_time = time.monotonic()
                    self._sequence += 1
                    self._condition.notify_all()
        except Exception:
            logger.exception("读取摄像头视频流失败")
        finally:
            with self._condition:
                self._ended = True
                self._condition.notify_all()

    def _stop_locked(self):
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if self._reader is not None:
                self._reader.join(timeout=3)
            process.stdout.close()
        self._process = None
        self._reader = None
        with self._condition:
            self._ended = True
            self._frame = None
            self._condition.notify_all()

    def _start(self):
        with self._lifecycle:
            if self._closed:
                raise CameraError("摄像头服务正在退出")
            if self._process is not None and self._process.poll() is None and not self._ended:
                return
            self._stop_locked()
            self._process = subprocess.Popen(
                [
                    "rpicam-vid", "--camera", "0", "--nopreview", "--timeout", "0",
                    "--width", "640", "--height", "480", "--framerate", "2",
                    "--codec", "mjpeg", "--quality", "85", "--flush", "--output", "-",
                ],
                stdout=subprocess.PIPE, bufsize=0,
                # Camera diagnostics go to the service log, never into JPEG data.
            )
            with self._condition:
                self._ended = False
                self._sequence = 0
                self._ready_after = time.monotonic() + 1.5
            self._reader = threading.Thread(
                target=self._read, args=(self._process,), name="camera-reader", daemon=True
            )
            self._reader.start()

    def capture(self, timeout=10):
        self._start()
        try:
            with self._condition:
                previous = self._sequence
                deadline = time.monotonic() + timeout
                while True:
                    if self._ended or self._closed:
                        raise CameraError("摄像头视频流中断，请检查连接和服务日志")
                    # Require a new frame, not the cached frame from the previous cycle.
                    if self._sequence > previous and self._frame_time >= self._ready_after:
                        return self._frame
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("等待摄像头新画面超时")
                    self._condition.wait(remaining)
        except (CameraError, TimeoutError):
            with self._lifecycle:
                self._stop_locked()
            raise

    def close(self):
        with self._lifecycle:
            with self._condition:
                self._closed = True
                self._condition.notify_all()
            self._stop_locked()
