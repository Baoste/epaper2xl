"""Download verified OpenCV models and cache imgs/head_photo.jpg's face feature."""

import os
import urllib.request

from face_compare import FaceComparer, MODEL_DIR, MODELS, file_hash


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    for name, (folder, expected) in MODELS.items():
        target = MODEL_DIR / name
        if target.is_file() and file_hash(target) == expected:
            continue
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{folder}/{name}"
        temporary = target.with_suffix(".download")
        print(f"Downloading {name} ...", flush=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as response, open(temporary, "wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            if file_hash(temporary) != expected:
                raise RuntimeError(f"Model checksum mismatch: {name}")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        license_url = f"https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/{folder}/LICENSE"
        with urllib.request.urlopen(license_url, timeout=30) as response:
            (MODEL_DIR / f"{folder}.LICENSE").write_bytes(response.read())
    comparer = FaceComparer()
    comparer.prepare_reference()
    print(f"Reference feature ready: {comparer.cache_path}")


if __name__ == "__main__":
    main()
