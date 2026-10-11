from datetime import datetime
import threading
import unittest
from unittest.mock import Mock, patch

import server
from presence_monitor import REST_TEXT, is_rest_time, run_monitor, seconds_to_boundary


class RestTests(unittest.TestCase):
    def test_time_boundaries(self):
        for hour, minute, second, resting, seconds in (
            (7, 59, 59, True, 1), (8, 0, 0, False, 14 * 3600),
            (21, 59, 59, False, 1), (22, 0, 0, True, 10 * 3600),
            (0, 0, 0, True, 8 * 3600),
        ):
            with self.subTest(hour=hour):
                now = datetime(2026, 10, 11, hour, minute, second)
                self.assertEqual(is_rest_time(now), resting)
                self.assertEqual(seconds_to_boundary(now), seconds)

    def test_night_boot_closes_camera_without_detection(self):
        capture, display, pause, stop = Mock(), Mock(), Mock(), Mock()
        stop.is_set.return_value = False
        stop.wait.return_value = True
        run_monitor(capture, display, stop, pause, now=lambda: datetime(2026, 10, 11, 23))
        capture.assert_not_called()
        pause.assert_called_once()
        display.assert_called_once_with(REST_TEXT)
        stop.wait.assert_called_once_with(60)

    def test_daytime_wait_is_capped_at_22(self):
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.return_value = True
        capture = Mock(return_value={"status": "ok", "similarity": .9})
        run_monitor(capture, Mock(), stop, Mock(), now=lambda: datetime(2026, 10, 11, 21, 59, 59))
        stop.wait.assert_called_once_with(1)

    def test_inflight_result_after_22_does_not_replace_rest_message(self):
        clock = [datetime(2026, 10, 11, 21, 59, 59)]
        stop, display, pause = Mock(), Mock(), Mock()
        stop.is_set.return_value = False
        stop.wait.return_value = True

        def capture():
            clock[0] = datetime(2026, 10, 11, 22)
            return {"status": "ok", "similarity": .9}

        run_monitor(capture, display, stop, pause, now=lambda: clock[0])
        display.assert_called_once_with(REST_TEXT)
        pause.assert_called_once()

    def test_8am_resumes_with_a_reset_low_score_streak(self):
        clock = [datetime(2026, 10, 11, 21, 59, 58)]
        stop, display, pause = Mock(), Mock(), Mock()
        stop.is_set.return_value = False
        capture = Mock(return_value={"status": "ok", "similarity": .1})
        waits = []

        def wait(seconds):
            waits.append(seconds)
            if len(waits) == 1:
                clock[0] = datetime(2026, 10, 11, 22)
            elif len(waits) == 2:
                clock[0] = datetime(2026, 10, 12, 8)
            return len(waits) == 4

        stop.wait.side_effect = wait
        run_monitor(capture, display, stop, pause, now=lambda: clock[0])
        self.assertEqual(waits, [2, 60, 2, 2])
        self.assertEqual(capture.call_count, 3)
        display.assert_called_once_with(REST_TEXT)

    def test_web_capture_does_not_wake_camera_at_night(self):
        with patch("server.is_rest_time", return_value=True), \
                patch.object(server.camera, "pause") as pause, \
                patch.object(server.camera, "capture") as capture, \
                patch("server.compare_photo") as compare:
            response = server.app.test_client().post("/capture")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["status"], "resting")
        pause.assert_called_once()
        capture.assert_not_called()
        compare.assert_not_called()
        self.assertFalse(server.camera_lock.locked())

    def test_night_message_takes_over_movie_and_is_not_repeated(self):
        active = Mock()
        active.poll.return_value = None
        finished = Mock(returncode=0)
        finished.poll.return_value = 0
        with patch("server.is_rest_time", return_value=True), \
                patch("server.service_stopping", threading.Event()), \
                patch("server.monitor_stop", threading.Event()), \
                patch("server.display_process", active), \
                patch("server.display_revision", 0), \
                patch("server.presence_displayed", None), \
                patch("server.subprocess.Popen", return_value=finished) as spawn:
            server.show_presence(REST_TEXT)
            server.show_presence(REST_TEXT)
            active.terminate.assert_called_once()
            spawn.assert_called_once()
            self.assertEqual(spawn.call_args.args[0][-1], REST_TEXT)


if __name__ == "__main__":
    unittest.main()
