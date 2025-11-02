import os, sys, time, lmdb, signal, logging, json
from io import BytesIO
from PIL import Image
from omni_epd import displayfactory, EPDNotFoundError
import configargparse


# ---- 初始化日志 ----
logging.basicConfig(level=getattr(logging, "INFO"), format="%(levelname)s: %(message)s")
logger = logging.getLogger("LMDBPlayer")

# ---- 初始化 ePaper ----
try:
    epd = displayfactory.load_display_driver("waveshare_epd.epd7in5_V2")
except EPDNotFoundError:
    valid = displayfactory.list_supported_displays()
    logger.error(f"无法加载 ePaper 驱动，请检查名称。可用驱动：\n{valid}")
    sys.exit(1)


frame_state_file = "/home/baoste/epaper2xl/state.json"
current_frame = 0

def save_frame_state():
    try:
        with open(frame_state_file, "w") as f:
            json.dump({"frame": current_frame}, f)
        logger.info(f"已保存播放进度: frame={current_frame}")
    except Exception as e:
        logger.error(f"保存帧数失败: {e}")

def load_frame_state():
    global current_frame
    if os.path.exists(frame_state_file):
        try:
            with open(frame_state_file, "r") as f:
                data = json.load(f)
                current_frame = data.get("frame", 0)
                logger.info(f"从上次进度恢复: frame={current_frame}")
        except Exception as e:
            logger.warning(f"无法读取上次进度: {e}")


def graceful_exit(signum=None, frame=None):
    logger.info("Exiting ...")
    save_frame_state()
    epd.close()
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)


def main():
    load_frame_state()

    # ---- 参数解析 ----
    parser = configargparse.ArgumentParser(
        description="Play LMDB 1-bit frames on ePaper display",
    )
    parser.add_argument("--lmdb_dir", default="/home/baoste/lmdb_frames", help="Directory containing LMDB files")
    parser.add_argument("--base_name", default="frame_dataset", help="LMDB file prefix")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between frames (seconds)")
    parser.add_argument("--frame_start", type=int, default=current_frame, help="Start frame")
    args = parser.parse_args()

    # ---- 获取 LMDB 列表 ----
    lmdb_files = sorted([
        f for f in os.listdir(args.lmdb_dir)
        if f.startswith(args.base_name) and f.endswith(".lmdb")
    ])
    if not lmdb_files:
        logger.error("Can NOT find any LMDB files")
        sys.exit(1)
    logger.info(f"Detected {len(lmdb_files)} LMDB file(s).")

    # ---- 主播放循环 ----
    while True:
        total = 0
        for lmdb_name in lmdb_files:
            full_path = os.path.join(args.lmdb_dir, lmdb_name)
            logger.info(f"Opening {lmdb_name} ...")

            try:
                env = lmdb.open(full_path, readonly=True, lock=False, readahead=False, max_readers=1)
            except Exception as e:
                logger.error(f"Can NOT open {lmdb_name}: {e}")
                continue

            with env.begin(buffers=False) as txn:
                cursor = txn.cursor()

                if not cursor.first():
                    env.close()
                    logger.warning(f"{lmdb_name} is empty, skipping.")
                    continue
                
                total += txn.stat()["entries"]
                if args.frame_start > total:
                    env.close()
                    current_frame = total
                    logger.info(f"Skip {lmdb_name}")
                    continue
                
                logger.info(f"Start playing ...")
                for key, val in cursor:
                    if not val:
                        continue

                    current_frame += 1
                    if args.frame_start > current_frame:
                        continue

                    try:
                        img = Image.open(BytesIO(val))
                        epd.prepare()
                        epd.display(img)
                        time.sleep(args.delay)
                        epd.sleep()

                    except Exception as e:
                        logger.warning(f"Frame {key.decode('utf-8', errors='ignore')} failed: {e}")
                        continue

            env.close()
            logger.info(f"Finished {lmdb_name}")

if __name__ == "__main__":
    main()
