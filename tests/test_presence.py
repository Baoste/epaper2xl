import threading
import unittest
from unittest.mock import Mock, patch

import server
from presence_monitor import ABSENT_TEXT, OWNER_TEXT, VISITOR_TEXT, PresencePolicy, run_monitor


class PresenceTests(unittest.TestCase):
    def test_three_consecutive_low_scores_and_intervals(self):
        policy = PresencePolicy()
        low = {"status": "ok", "similarity": .37999}
        self.assertEqual(policy.observe(low), (1, None))
        self.assertEqual(policy.observe(low), (1, None))
        self.assertEqual(policy.observe(low), (1, VISITOR_TEXT))
        self.assertEqual(policy.observe(low), (1, VISITOR_TEXT))
        self.assertEqual(policy.observe({"status": "ok", "similarity": .38}), (60, OWNER_TEXT))
        self.assertEqual(policy.observe(low), (1, None))

    def test_no_face_errors_and_multiple_faces_reset_streak(self):
        for status in ("no_face", "multiple_faces", "error", "unavailable"):
            with self.subTest(status=status):
                policy = PresencePolicy()
                low = {"status": "ok", "similarity": .1}
                policy.observe(low)
                policy.observe(low)
                self.assertEqual(policy.observe({"status": status}), (5, ABSENT_TEXT if status == "no_face" else None))
                self.assertEqual(policy.observe(low), (1, None))

    def test_invalid_scores_do_not_identify_owner_or_visitor(self):
        for score in (None, "0.5", float("nan"), float("inf")):
            self.assertEqual(PresencePolicy().observe({"status": "ok", "similarity": score}), (5, None))

    def test_wait_happens_after_each_processing_and_display(self):
        events = []
        results = iter([{"status": "ok", "similarity": .2}] * 3 + [
            {"status": "ok", "similarity": .9}, {"status": "no_face"},
        ])
        stop = Mock()
        stop.is_set.return_value = False
        waits = []

        def capture():
            events.append("capture")
            return next(results)

        def wait(seconds):
            events.append(seconds)
            waits.append(seconds)
            return len(waits) == 5

        stop.wait.side_effect = wait
        run_monitor(capture, events.append, stop)
        self.assertEqual(events, ["capture", 1, "capture", 1, "capture", VISITOR_TEXT, 1,
                                  "capture", OWNER_TEXT, 60, "capture", ABSENT_TEXT, 5])

    def test_shutdown_during_capture_does_not_display(self):
        stop = threading.Event()
        display = Mock()

        def capture():
            stop.set()
            return {"status": "no_face"}

        run_monitor(capture, display, stop)
        display.assert_not_called()


class PresenceDisplayTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("display_process", None), ("display_revision", 0),
                            ("presence_displayed", None), ("monitor_stop", threading.Event()),
                            ("service_stopping", threading.Event())):
            patcher = patch.object(server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_same_text_only_refreshes_once_and_manual_change_invalidates_it(self):
        proc = Mock(returncode=0)
        proc.poll.return_value = 0
        with patch.object(server.subprocess, "Popen", return_value=proc) as spawn:
            server.show_presence(OWNER_TEXT)
            server.show_presence(OWNER_TEXT)
            self.assertEqual(spawn.call_count, 1)
            server.start_display(["manual"])
            server.show_presence(OWNER_TEXT)
            self.assertEqual(spawn.call_count, 3)

    def test_automatic_display_does_not_interrupt_active_display(self):
        proc = Mock()
        proc.poll.return_value = None
        server.display_process = proc
        with patch.object(server.subprocess, "Popen") as spawn:
            server.show_presence(ABSENT_TEXT)
            spawn.assert_not_called()
            proc.terminate.assert_not_called()

    def test_failed_display_is_retried(self):
        proc = Mock(returncode=1)
        proc.poll.return_value = 1
        with patch.object(server.subprocess, "Popen", return_value=proc) as spawn:
            server.show_presence(OWNER_TEXT)
            server.show_presence(OWNER_TEXT)
            self.assertEqual(spawn.call_count, 2)


if __name__ == "__main__":
    unittest.main()
