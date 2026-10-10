import logging
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from io import BytesIO
from typing import List, Optional, Tuple

from PIL import Image
from flask import Flask, Response, send_from_directory, redirect, request, jsonify
from werkzeug.utils import secure_filename
from face_compare import compare_photo

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("LMDBPlayer")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = "/home/baoste/epaper-env/bin/python"
DISPLAY_IMG = os.path.join(BASE_DIR, "display_img.py")
DISPLAY_MOVIE = os.path.join(BASE_DIR, "display_movie.py")
TMP_DIR = os.path.join(BASE_DIR, ".img_tmp")

WIFI_CHECK_INTERVAL = 10.0
WIFI_INTERFACE = ""  # 留空：任意 Wi-Fi 连接成功即可；也可填 "wlan0"
WELCOME_TEXT = "这里是徐一帆的工位 ^ ^"

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

display_process: Optional[subprocess.Popen] = None
display_lock = threading.Lock()
camera_lock = threading.Lock()
monitor_stop = threading.Event()
service_stopping = threading.Event()


def _stop_display_locked() -> None:
    """调用者必须持有 display_lock。"""
    global display_process
    if display_process is None:
        return
    if display_process.poll() is None:
        logger.info("正在结束显示进程...")
        display_process.terminate()
        try:
            display_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            display_process.kill()
            display_process.wait(timeout=3)
    display_process = None


def stop_display() -> None:
    with display_lock:
        _stop_display_locked()


def start_display(cmd: List[str], *, startup: bool = False) -> Optional[subprocess.Popen]:
    """串行管理显示进程；网页操作优先于开机状态显示。"""
    global display_process
    with display_lock:
        if service_stopping.is_set():
            raise RuntimeError("服务正在退出")
        if startup:
            if monitor_stop.is_set():
                return None
            # 自动刷新不打断尚未结束的刷屏，下一轮再显示最新状态。
            if display_process is not None and display_process.poll() is None:
                logger.info("上一次显示尚未结束，本轮不启动新的显示进程")
                return None
        else:
            # 用户通过网页主动操作后，本次启动不再显示 Wi-Fi 提示。
            monitor_stop.set()

        _stop_display_locked()
        display_process = subprocess.Popen(
            cmd, stdout=sys.stdout, stderr=sys.stderr, text=True
        )
        return display_process


def get_wifi_status() -> Tuple[bool, str]:
    """只读查询 NetworkManager；不主动重连，也不检测互联网。"""
    env = os.environ.copy()
    env["LC_ALL"] = "C"  # 固定状态输出语言，避免中文系统解析失败。
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-c", "no", "-f", "DEVICE,TYPE,STATE", "device", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=env,
        )
    except FileNotFoundError:
        return False, "无法检测 Wi-Fi：找不到 nmcli"
    except subprocess.TimeoutExpired:
        return False, "Wi-Fi 状态检测超时"
    except OSError as exc:
        logger.warning("无法运行 nmcli：%s", exc)
        return False, "Wi-Fi 状态检测失败"

    if result.returncode != 0:
        logger.warning("nmcli 检测失败：%s", result.stderr.strip())
        return False, "Wi-Fi 状态未知：请检查 NetworkManager"

    found_wifi = False
    connecting = False
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        device, device_type, state = parts
        if device_type not in ("wifi", "802-11-wireless"):
            continue
        if WIFI_INTERFACE and device != WIFI_INTERFACE:
            continue
        found_wifi = True
        # 不能用 'connected' in state，否则 disconnected 也会被误判。
        if state == "connected" or state.startswith("connected ("):
            return True, "Wi-Fi 已连接"
        if state.startswith("connecting"):
            connecting = True

    if not found_wifi:
        return False, "未发现指定无线网卡" if WIFI_INTERFACE else "未发现无线网卡"
    if connecting:
        return False, "Wi-Fi 正在连接"
    return False, "Wi-Fi 未连接：等待自动连接"


def wifi_startup_monitor() -> None:
    """每 10 秒检查一次；成功后显示工位文字并结束。"""
    check_count = 0
    connected_once = False
    pending_process = None
    pending_is_welcome = False

    while not monitor_stop.is_set():
        tick = time.monotonic()
        try:
            # 确认上次显示进程的退出结果，避免把启动成功当成显示成功。
            if pending_process is not None:
                returncode = pending_process.poll()
                if returncode is not None:
                    if returncode != 0:
                        logger.error("显示进程退出码为 %s，将重试显示", returncode)
                    elif pending_is_welcome:
                        logger.info("工位文字显示程序正常结束，停止开机状态刷新")
                        return
                    pending_process = None

            if not connected_once:
                check_count += 1
                connected_once, status = get_wifi_status()
                logger.info("Wi-Fi 检测第 %d 次：%s", check_count, status)
                text = (
                    WELCOME_TEXT if connected_once
                    else f"{status}\n检测次数：{check_count}"
                )
            else:
                # 曾检测到连接成功后，不再回到等待连接画面。
                text = WELCOME_TEXT

            cmd = [PYTHON, DISPLAY_IMG, "--img_path", "", "--text", text]
            proc = start_display(cmd, startup=True)
            if proc is not None:
                pending_process = proc
                pending_is_welcome = connected_once
                logger.info("已启动文字显示：%s", text.replace("\n", " / "))
        except Exception:
            if not monitor_stop.is_set():
                logger.exception("开机状态显示异常，下一轮重试")

        # 扣除本轮检测耗时；停止服务或网页接管时可立即结束等待。
        delay = max(0.1, WIFI_CHECK_INTERVAL - (time.monotonic() - tick))
        if monitor_stop.wait(delay):
            return


@app.route("/")
def index():
    return redirect("/index.html")


@app.route("/<path:filename>")
def serve_file(filename):
    return send_from_directory(app.template_folder, filename)


@app.route("/play_movie", methods=["POST"])
def play_movie():
    try:
        start_display([PYTHON, DISPLAY_MOVIE])
        return jsonify({"status": "ok", "message": "正在播放电影..."})
    except Exception as exc:
        logger.exception("启动播放失败")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/capture", methods=["POST"])
def capture_photo():
    if not camera_lock.acquire(blocking=False):
        return jsonify(status="error", message="摄像头正在拍摄，请稍后重试"), 409

    try:
        result = subprocess.run(
            [
                "rpicam-still", "--camera", "0", "--nopreview",
                "--timeout", "1500", "--width", "640", "--height", "480",
                "--encoding", "jpg", "--quality", "85", "--output", "-",
            ],
            capture_output=True,
            timeout=20,
            check=True,
        )
        if not result.stdout.startswith(b"\xff\xd8\xff"):
            logger.error("摄像头未返回 JPEG 图片")
            return jsonify(status="error", message="摄像头未返回有效照片，请重试"), 502
        # 逆时针旋转 90 度，完整保留画面，输出尺寸变为 480×640。
        output = BytesIO()
        try:
            with Image.open(BytesIO(result.stdout)) as photo:
                with photo.transpose(Image.Transpose.ROTATE_90) as upright:
                    upright.save(output, format="JPEG", quality=85)
        except OSError:
            logger.exception("摄像头照片解码失败")
            return jsonify(status="error", message="照片解码失败，请重试"), 502
        jpeg = output.getvalue()
        comparison = compare_photo(jpeg)
        # 照片和对应结果在同一个响应返回，避免多客户端串图。
        return Response(
            jpeg, mimetype="image/jpeg",
            headers={
                "Cache-Control": "no-store",
                "X-Face-Result": json.dumps(comparison, ensure_ascii=True),
            },
        )
    except FileNotFoundError:
        return jsonify(status="error", message="找不到 rpicam-still，请先安装 rpicam-apps"), 503
    except subprocess.TimeoutExpired:
        logger.warning("摄像头拍摄超时")
        return jsonify(status="error", message="拍摄超时，请检查摄像头连接或占用情况"), 504
    except subprocess.CalledProcessError as exc:
        logger.error("拍摄失败：%s", (exc.stderr or b"").decode("utf-8", errors="replace"))
        return jsonify(status="error", message="拍摄失败，请检查摄像头是否被占用，并查看服务日志"), 503
    except OSError:
        logger.exception("无法启动摄像头")
        return jsonify(status="error", message="无法启动摄像头，请查看服务日志"), 503
    finally:
        camera_lock.release()


@app.route("/upload", methods=["POST"])
def upload():
    text = request.form.get("text", "").strip()
    file = request.files.get("image")
    has_image = bool(file and file.filename)
    if not has_image and not text:
        return jsonify({"status": "error", "message": "未提供图片或文字"}), 400

    tmp_path = ""
    try:
        if has_image:
            os.makedirs(TMP_DIR, exist_ok=True)
            filename = secure_filename(file.filename) or "image"
            tmp_path = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}_{filename}")
            file.save(tmp_path)
            logger.info("Received file: %s", tmp_path)
        start_display([PYTHON, DISPLAY_IMG, "--img_path", tmp_path, "--text", text])
        return jsonify({"status": "ok", "message": "已启动图片或文字显示"})
    except Exception as exc:
        logger.exception("启动显示失败")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/shutdown", methods=["POST"])
def shutdown_pi():
    try:
        monitor_stop.set()
        stop_display()
        subprocess.Popen(["bash", "-c", "sleep 5 && sudo shutdown -h now"])
        return jsonify({"status": "ok", "message": "5 秒后关机..."})
    except Exception as exc:
        logger.exception("关机失败")
        return jsonify({"status": "error", "message": str(exc)}), 500


def graceful_exit(signum, frame):
    # 信号处理函数不拿锁；资源清理由下面的 finally 完成。
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    monitor_thread = threading.Thread(
        target=wifi_startup_monitor, name="wifi-startup-monitor", daemon=True
    )
    try:
        monitor_thread.start()
        logger.info("Flask server running at http://0.0.0.0:80")
        # 避免自动重载器重复启动监控线程。
        app.run(host="0.0.0.0", port=80, debug=False, use_reloader=False)
    finally:
        service_stopping.set()
        monitor_stop.set()
        monitor_thread.join(timeout=6)
        stop_display()
