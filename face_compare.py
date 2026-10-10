"""Local YuNet + SFace comparison. Models and reference features are reused."""

import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
import time
import zipfile

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
REFERENCE = BASE_DIR / "ImageYF.png"
CACHE = BASE_DIR / ".face_cache" / "ImageYF.npz"
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "face_detection_yunet", "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    ),
    "face_recognition_sface_2021dec_int8.onnx": (
        "face_recognition_sface", "2b0e941e6f16cc048c20aee0c8e31f569118f65d702914540f7bfdc14048d78a"
    ),
}
logger = logging.getLogger(__name__)


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FaceSetupError(RuntimeError):
    pass


class FaceComparer:
    """Caller serializes access: OpenCV networks are not shared concurrently."""

    def __init__(self, reference=REFERENCE, cache=CACHE, model_dir=MODEL_DIR):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise FaceSetupError("缺少 OpenCV 或 NumPy，请按 README 安装人脸比对依赖") from exc
        if not (4, 8) <= tuple(int(n) for n in cv2.__version__.split(".")[:2]) < (5, 0):
            raise FaceSetupError("需要 OpenCV 4.8 或更新的 4.x 版本，请按 README 安装")
        self.cv = cv2
        self.np = np
        self.reference_path = Path(reference)
        self.cache_path = Path(cache)
        self.reference_feature = None
        self.reference_stat = None
        for name, (_, expected) in MODELS.items():
            path = Path(model_dir) / name
            if not path.is_file() or file_hash(path) != expected:
                raise FaceSetupError("人脸模型缺失或不完整，请先运行 python prepare_face.py")
        # Limit CPU contention with Flask and the ePaper display process.
        cv2.setNumThreads(2)
        self.detector = cv2.FaceDetectorYN.create(
            str(Path(model_dir) / next(iter(MODELS))), "", (320, 320), 0.85, 0.3, 500
        )
        self.recognizer = cv2.FaceRecognizerSF.create(
            str(Path(model_dir) / "face_recognition_sface_2021dec_int8.onnx"), ""
        )

    def detect(self, image):
        """Detect in a fixed 320px canvas, map landmarks back to original pixels."""
        h, w = image.shape[:2]
        scale = min(320 / w, 320 / h, 1.0)
        width, height = max(1, round(w * scale)), max(1, round(h * scale))
        canvas = self.np.zeros((320, 320, 3), dtype=self.np.uint8)
        canvas[:height, :width] = self.cv.resize(image, (width, height))
        _, faces = self.detector.detect(canvas)
        if faces is None:
            return []
        faces = faces.copy()
        faces[:, 0:14:2] *= w / width
        faces[:, 1:14:2] *= h / height
        return faces

    def feature(self, image, face):
        aligned = self.recognizer.alignCrop(image, face)
        return self.normalize(self.recognizer.feature(aligned))

    def normalize(self, feature):
        feature = self.np.asarray(feature, dtype=self.np.float32).reshape(-1)
        norm = self.np.linalg.norm(feature)
        if feature.size != 128 or not self.np.isfinite(feature).all() or norm < 1e-8:
            raise ValueError("Invalid face feature")
        return feature / norm

    def prepare_reference(self):
        try:
            stat = self.reference_path.stat()
        except FileNotFoundError as exc:
            raise FaceSetupError("找不到参考照片 ImageYF.png") from exc
        signature = (stat.st_mtime_ns, stat.st_size)
        if self.reference_feature is not None and signature == self.reference_stat:
            return
        key = json.dumps({
            "reference": file_hash(self.reference_path),
            "models": MODELS,
            "preprocessing": "320-letterbox-original-align-v1",
        }, sort_keys=True)
        try:
            with self.np.load(self.cache_path, allow_pickle=False) as cached:
                if cached["key"].item() == key:
                    self.reference_feature = self.normalize(cached["feature"])
                    self.reference_stat = signature
                    return
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
            pass

        from PIL import Image, ImageOps
        with Image.open(self.reference_path) as photo:
            rgb = self.np.array(ImageOps.exif_transpose(photo).convert("RGB"))
        image = self.cv.cvtColor(rgb, self.cv.COLOR_RGB2BGR)
        faces = self.detect(image)
        if len(faces) != 1:
            raise FaceSetupError(f"参考照片需恰好有一张清晰人脸，当前检测到 {len(faces)} 张")
        self.reference_feature = self.feature(image, faces[0])
        self.reference_stat = signature
        # Atomic write; a read-only deployment can still reuse the in-memory feature.
        temporary = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.cache_path.parent, suffix=".npz", delete=False) as stream:
                temporary = stream.name
                self.np.savez(stream, key=key, feature=self.reference_feature)
            os.replace(temporary, self.cache_path)
        except OSError:
            logger.warning("参考特征无法写入磁盘，本次服务仍使用内存缓存", exc_info=True)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def compare(self, jpeg):
        self.prepare_reference()
        image = self.cv.imdecode(self.np.frombuffer(jpeg, dtype=self.np.uint8), self.cv.IMREAD_COLOR)
        if image is None:
            raise ValueError("Invalid JPEG")
        faces = self.detect(image)
        if len(faces) == 0:
            return {"status": "no_face", "message": "未检测到人脸，请靠近摄像头并保持正面"}
        if len(faces) > 1:
            return {"status": "multiple_faces", "message": "检测到多张人脸，请只保留一人入镜"}
        feature = self.feature(image, faces[0])
        score = float(self.np.clip(self.np.dot(self.reference_feature, feature), -1, 1))
        return {"status": "ok", "similarity": round(score, 4)}


_comparer = None


def compare_photo(jpeg):
    """Called under server.camera_lock; failure must not hide a captured photo."""
    global _comparer
    started = time.perf_counter()
    try:
        if _comparer is None:
            _comparer = FaceComparer()
        result = _comparer.compare(jpeg)
    except FaceSetupError as exc:
        result = {"status": "unavailable", "message": str(exc)}
    except Exception:
        logger.exception("人脸比对失败")
        result = {"status": "error", "message": "人脸比对失败，请查看服务日志"}
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return result
