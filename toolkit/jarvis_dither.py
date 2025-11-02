"""
Jarvis–Judice–Ninke (JJN) Dithering implementation for grayscale images.
Used to convert 8-bit grayscale to 1-bit black/white with smooth diffusion.
"""

import io
import numpy as np
# from numba import jit
from PIL import Image

# ===== Config =====
TARGET_W, TARGET_H = 800, 480
RATIO = TARGET_W / TARGET_H


# ===== Core algorithm =====
# @jit(nopython=True)
def jarvis_dither_core(arr, h, w):
    """
    Main JJN diffusion kernel (Numba accelerated)
    """
    for y in range(h):
        for x in range(w):
            old_pixel = arr[y, x]
            old_pixel = 0.0 if old_pixel < 0.0 else (255.0 if old_pixel > 255.0 else old_pixel)
            new_pixel = 255.0 if old_pixel >= 128.0 else 0.0
            error = old_pixel - new_pixel
            arr[y, x] = new_pixel

            # distribute error to neighbors
            # same line
            if x + 1 < w:
                arr[y, x + 1] += error * 7 / 48
            if x + 2 < w:
                arr[y, x + 2] += error * 5 / 48

            # next line
            if y + 1 < h:
                if x - 2 >= 0:
                    arr[y + 1, x - 2] += error * 3 / 48
                if x - 1 >= 0:
                    arr[y + 1, x - 1] += error * 5 / 48
                arr[y + 1, x] += error * 7 / 48
                if x + 1 < w:
                    arr[y + 1, x + 1] += error * 5 / 48
                if x + 2 < w:
                    arr[y + 1, x + 2] += error * 3 / 48

            # line +2
            if y + 2 < h:
                if x - 2 >= 0:
                    arr[y + 2, x - 2] += error * 1 / 48
                if x - 1 >= 0:
                    arr[y + 2, x - 1] += error * 3 / 48
                arr[y + 2, x] += error * 5 / 48
                if x + 1 < w:
                    arr[y + 2, x + 1] += error * 3 / 48
                if x + 2 < w:
                    arr[y + 2, x + 2] += error * 1 / 48
    return arr


def jarvis_dither(img_array):
    """Grayscale numpy array → JJN dithered binary array"""
    arr = img_array.astype(np.float32)
    h, w = arr.shape
    arr = jarvis_dither_core(arr, h, w)
    return arr.astype(np.uint8)


# ===== Helper functions =====
def compute_center_crop_box(width, height):
    """Center crop to match aspect ratio"""
    src_ratio = width / height
    if src_ratio > RATIO:  # too wide
        new_h = height
        new_w = int(round(RATIO * new_h))
    else:  # too tall
        new_w = width
        new_h = int(round(new_w / RATIO))
    left = (width - new_w) // 2
    top = (height - new_h) // 2
    right = left + new_w
    bottom = top + new_h
    return (left, top, right, bottom)


def process_frame_to_1bpp(gray_image, target_size=(TARGET_W, TARGET_H)):
    """
    Apply JJN dithering and output 1-bit BMP bytes
    """
    # Convert to grayscale PIL Image
    if isinstance(gray_image, np.ndarray):
        pil_img = Image.fromarray(gray_image)
    else:
        pil_img = gray_image
    if pil_img.mode != "L":
        pil_img = pil_img.convert("L")

    # Center crop and resize
    w, h = pil_img.size
    crop_box = compute_center_crop_box(w, h)
    pil_img = pil_img.crop(crop_box)
    pil_img = pil_img.resize(target_size, resample=Image.Resampling.LANCZOS)

    # Apply dithering
    arr = np.array(pil_img)
    dithered = jarvis_dither(arr)

    # Convert to 1-bit image and save to buffer
    dithered_img = Image.fromarray(dithered).convert("1")
    buf = io.BytesIO()
    dithered_img.save(buf, format="BMP")
    return buf.getvalue()
