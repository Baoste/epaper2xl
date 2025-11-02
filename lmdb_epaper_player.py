import os, sys, time, lmdb, signal, logging
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


def graceful_exit(signum=None, frame=None):
    logger.info("Exiting ...")
    epd.close()
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)


def main():
    # ---- 参数解析 ----
    parser = configargparse.ArgumentParser(
        description="Play LMDB 1-bit frames on ePaper display",
    )
    parser.add_argument("--lmdb_dir", default="/home/baoste/lmdb_frames", help="Directory containing LMDB files")
    parser.add_argument("--base_name", default="frames_dataset", help="LMDB file prefix")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between frames (seconds)")
    parser.add_argument("--loop", action="store_true", default=True, help="Loop playback")
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
                    logger.warning(f"{lmdb_name} is empty, skipping.")
                    continue

                for key, val in cursor:
                    if not val:
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
