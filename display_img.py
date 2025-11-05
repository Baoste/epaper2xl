import sys, logging, os, time, signal
from io import BytesIO
from toolkit.jarvis_dither import process_frame_to_1bpp
from PIL import Image, ImageDraw, ImageFont
from omni_epd import displayfactory, EPDNotFoundError
import configargparse
import textwrap

# init logger
logging.basicConfig(level=getattr(logging, "INFO"), format="%(levelname)s: %(message)s")
logger = logging.getLogger("LMDBPlayer")

# ---- 初始化 ePaper ----
try:
    epd = displayfactory.load_display_driver("waveshare_epd.epd7in5_V2")
except EPDNotFoundError:
    valid = displayfactory.list_supported_displays()
    logger.error(f"无法加载 ePaper 驱动，请检查名称。可用驱动：\n{valid}")
    sys.exit(1)


def graceful_exit(signum=None, frame=None):
    logger.info("Exiting ...")
    epd.close()
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)


def main():
    parser = configargparse.ArgumentParser(
        description="Example for configargparse demo"
    )

    parser.add_argument("--img_path", type=str, default="", help="Image to display")
    parser.add_argument("--text", type=str, default="", help="Text to display")
    args = parser.parse_args()
    
    img = None

    if args.img_path:
        img = Image.open(args.img_path).convert("L")
        val = process_frame_to_1bpp(img)
        img = Image.open(BytesIO(val))

    elif args.text:
        img = Image.new("1", (800, 480), 255)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/home/baoste/fonts/FangZhengFengYa.TTF", 64)
        except:
            font = ImageFont.load_default()

        text_width = (len(args.text) // 2 + 1) if len(args.text) > 8 else 8

        wrapped_text = textwrap.fill(args.text, width=text_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=10, align="center")
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pos = ((800 - text_w) // 2, (480 - text_h) // 2)
        draw.multiline_text(pos, wrapped_text, font=font, fill=0, spacing=10, align="center")

    if img:
        epd.prepare()
        epd.display(img)
        time.sleep(3)
        epd.sleep()
        logger.info("Displayed on ePaper.")

    if args.img_path and os.path.exists(args.img_path):
        os.remove(args.img_path)
        logger.info("Temporary file deleted.")


if __name__ == "__main__":
    main()
