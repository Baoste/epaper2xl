import sys, logging, os, time, signal, subprocess
from io import BytesIO
from flask import Flask, send_from_directory, redirect, request, jsonify
from PIL import Image, ImageDraw, ImageFont
from omni_epd import displayfactory, EPDNotFoundError
from toolkit.jarvis_dither import process_frame_to_1bpp


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

# init ePaper
try:
    epd = displayfactory.load_display_driver("waveshare_epd.epd7in5_V2")
except EPDNotFoundError:
    valid = displayfactory.list_supported_displays()
    logger.error(f"无法加载 ePaper 驱动，请检查名称。可用驱动：\n{valid}")
    sys.exit(1)

movie_process = None
def stop_movie():
    """停止正在播放的 lmdb_epaper_player.py"""
    global movie_process
    if movie_process and movie_process.poll() is None:
        logger.info("正在结束电影播放进程...")
        movie_process.terminate()
        try:
            movie_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            movie_process.kill()
        logger.info("播放进程已结束。")
        movie_process = None


def graceful_exit(signum=None, frame=None):
    logger.info("\nExiting ...")
    epd.close()
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
    global movie_process
    stop_movie()
    
    try:
        logger.info("Start to play the movie...")
        cmd = [
            "/home/baoste/epaper-env/bin/python",
            "/home/baoste/epaper2xl/lmdb_epaper_player.py"
        ]
        movie_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.success("Start SUCCESS")
        return jsonify({"status": "ok", "message": "正在播放电影..."})
    except Exception as e:
        logger.error(f"Start FAILED: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/upload", methods=["POST"])
def upload():
    stop_movie()

    os.makedirs("./.img_tmp", exist_ok=True)
    text = request.form.get("text", "").strip()
    file = request.files.get("image")

    tmp_path = None
    img = None

    try:
        if file and file.filename:  # 上传了图片
            tmp_path = f"./.img_tmp/{file.filename}"
            file.save(tmp_path)
            logger.info(f"Received file: {tmp_path}")
            img = Image.open(tmp_path).convert("L")
            val = process_frame_to_1bpp(img)
            img = Image.open(BytesIO(val))

        elif text:  # 没有图片，仅输入了文字
            logger.info(f"Creating text-only image: '{text}'")
            img = Image.new("1", (800, 480), 255)  # 白底灰度图
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("/home/baoste/fonts/WenYue-XinQingNianTi-W8-J-2.otf", 36)
            except:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pos = ((800 - text_w) // 2, (480 - text_h) // 2)
            draw.text(pos, text, font=font, fill=0)
        else:
            return jsonify({"status": "error", "message": "未提供图片或文字"}), 400

        if epd:
            epd.prepare()
            epd.display(img)
            time.sleep(3)
            epd.sleep()
            logger.info("Displayed on ePaper.")
        else:
            logger.warning("ePaper not initialized.")

        return jsonify({"status": "ok", "message": f"Displayed {'text' if not file else 'image'}"})

    except Exception as e:
        logger.error(f"Display failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.info("Temporary file deleted.")

@app.route("/shutdown", methods=["POST"])
def shutdown_pi():
    stop_movie()

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
