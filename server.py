import sys, logging, os, time, signal, subprocess
from flask import Flask, send_from_directory, redirect, request, jsonify

# init logger
logging.basicConfig(level=getattr(logging, "INFO"), format="%(levelname)s: %(message)s")
logger = logging.getLogger("LMDBPlayer")

# init flask
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

display_process = None
def stop_display():
    """停止正在播放的 lmdb_epaper_player.py"""
    global display_process
    if display_process and display_process.poll() is None:
        logger.info("正在结束播放进程...")
        display_process.terminate()
        try:
            display_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            display_process.kill()
        logger.info("播放进程已结束。")
        display_process = None


def graceful_exit(signum=None, frame=None):
    logger.info("\nExiting ...")
    stop_display()
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)


@app.route("/")
def index():
    return redirect("/index.html")

@app.route("/<path:filename>")
def serve_file(filename):
    return send_from_directory("templates", filename)

@app.route("/play_movie", methods=["POST"])
def play_movie():
    global display_process
    stop_display()
    
    try:
        logger.info("Start to play the movie...")
        cmd = [
            "/home/baoste/epaper-env/bin/python",
            "/home/baoste/epaper2xl/lmdb_epaper_player.py"
        ]
        display_process = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True
        )
        logger.info("Start SUCCESS")
        return jsonify({"status": "ok", "message": "正在播放电影..."})
    except Exception as e:
        logger.error(f"Start FAILED: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/upload", methods=["POST"])
def upload():
    global display_process
    stop_display()

    os.makedirs("./.img_tmp", exist_ok=True)
    text = request.form.get("text", "").strip()
    file = request.files.get("image")

    tmp_path = ""
    
    try:
        if file and file.filename:  # 上传了图片
            tmp_path = f"./.img_tmp/{file.filename}"
            file.save(tmp_path)
            logger.info(f"Received file: {tmp_path}")
        elif text:  # 没有图片，仅输入了文字
            logger.info(f"Creating text-only image: '{text}'")
        else:
            return jsonify({"status": "error", "message": "未提供图片或文字"}), 400

        cmd = [
            "/home/baoste/epaper-env/bin/python",
            "/home/baoste/epaper2xl/display.py",
            "--img_path", tmp_path,
            "--text", text
        ]
        display_process = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True
        )
        logger.info("Start SUCCESS")

        return jsonify({"status": "ok", "message": f"Displayed {'text' if not file else 'image'}"})

    except Exception as e:
        logger.error(f"Display failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/shutdown", methods=["POST"])
def shutdown_pi():
    stop_display()

    try:
        logger.warning("Received shutdown request! Shutting down system...")
        subprocess.Popen(["bash", "-c", "sleep 5 && sudo shutdown -h now"])
        return jsonify({"status": "ok", "message": "5 秒后关机..."})
    except Exception as e:
        logger.error(f"Shutdown failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print("Flask server running at http://0.0.0.0:80")
    app.run(host="0.0.0.0", port=80)
