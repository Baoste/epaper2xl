import uuid
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image

import face_compare
from face_compare import FaceComparer, FaceSetupError


class FaceCompareTests(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).resolve().parent / ("face-test-" + uuid.uuid4().hex)
        directory.mkdir()
        self.addCleanup(self.clean_directory, directory)
        # Supply fake network outputs while exercising real image/cache operations.
        self.engine = FaceComparer.__new__(FaceComparer)
        self.engine.cv = cv2
        self.engine.np = np
        self.engine.reference_path = directory / "reference.png"
        self.engine.cache_path = directory / "feature.npz"
        self.engine.reference_stat = None
        self.engine.reference_feature = None
        self.engine.detector = Mock()
        self.face = np.array([[40, 40, 60, 60, 50, 50, 80, 50, 65, 65, 55, 80, 75, 80, .99]], dtype=np.float32)
        self.engine.detector.detect.return_value = (None, self.face)
        self.engine.recognizer = Mock()
        self.engine.recognizer.feature.return_value = np.ones((1, 128), dtype=np.float32)
        Image.new("RGB", (480, 640)).save(self.engine.reference_path)

    @staticmethod
    def clean_directory(directory):
        for file in directory.iterdir():
            file.unlink()
        directory.rmdir()

    def test_landmarks_map_back_to_original_image(self):
        faces = self.engine.detect(np.zeros((640, 480, 3), dtype=np.uint8))
        np.testing.assert_allclose(faces[0, :14], self.face[0, :14] * 2)
        self.assertAlmostEqual(float(faces[0, 14]), .99, places=5)
        self.assertEqual(self.engine.detector.detect.call_args.args[0].shape, (320, 320, 3))

    def test_disk_cache_skips_reference_inference(self):
        self.engine.prepare_reference()
        self.assertTrue(self.engine.cache_path.exists())
        self.engine.reference_feature = None  # Simulate next service startup.
        self.engine.detector.reset_mock()
        self.engine.recognizer.reset_mock()
        self.engine.prepare_reference()
        self.engine.detector.detect.assert_not_called()
        self.engine.recognizer.feature.assert_not_called()

    def test_reference_change_rebuilds_cache(self):
        self.engine.prepare_reference()
        Image.new("RGB", (320, 240), "red").save(self.engine.reference_path)
        self.engine.prepare_reference()
        self.assertEqual(self.engine.recognizer.feature.call_count, 2)

    def test_invalid_cache_rebuilds(self):
        self.engine.cache_path.write_bytes(b"broken")
        self.engine.prepare_reference()
        self.engine.recognizer.feature.assert_called_once()

    def test_reference_must_have_exactly_one_face(self):
        for faces in (None, np.repeat(self.face, 2, axis=0)):
            with self.subTest(faces=faces):
                self.engine.detector.detect.return_value = (None, faces)
                with self.assertRaises(FaceSetupError):
                    self.engine.prepare_reference()

    def test_missing_reference_does_not_use_stale_feature(self):
        self.engine.prepare_reference()
        self.engine.reference_path.unlink()
        with self.assertRaises(FaceSetupError):
            self.engine.prepare_reference()

    def test_comparison_scores_and_face_counts(self):
        self.engine.prepare_reference()
        jpeg = self.engine.reference_path.read_bytes()
        self.assertAlmostEqual(self.engine.compare(jpeg)["similarity"], 1, places=6)
        self.engine.recognizer.reset_mock()
        for faces, status in ((None, "no_face"), (np.repeat(self.face, 2, axis=0), "multiple_faces")):
            with self.subTest(status=status):
                self.engine.detector.detect.return_value = (None, faces)
                self.assertEqual(self.engine.compare(jpeg)["status"], status)
                self.engine.recognizer.feature.assert_not_called()

    def test_setup_failure_is_reported_and_can_retry(self):
        with patch.object(face_compare, "_comparer", None), patch.object(face_compare, "FaceComparer") as factory:
            factory.side_effect = FaceSetupError("missing models")
            self.assertEqual(face_compare.compare_photo(b"")["status"], "unavailable")
            factory.side_effect = None
            factory.return_value.compare.return_value = {"status": "no_face"}
            self.assertEqual(face_compare.compare_photo(b"")["status"], "no_face")


if __name__ == "__main__":
    unittest.main()
