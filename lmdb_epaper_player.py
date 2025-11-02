import os, sys, time, lmdb, signal, random, logging
from io import BytesIO
from PIL import Image, ImageEnhance
from omni_epd import displayfactory, EPDNotFoundError
import configargparse


def main():
    # ---- 参数解析 ----
    parser = configargparse.ArgumentParser(
        description="Play LMDB 1-bit frames on ePaper display",
        default_config_files=["lmdb_epaper_player.config"]
    )
    parser.add_argument("--lmdb_dir", default="lmdb_frames", help="Directory containing LMDB files")
    parser.add_argument("--base_name", default="frames_dataset", help="LMDB file prefix")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between frames (seconds)")
    parser.add_argument("--loop", action="store_true", default=True, help="Loop playback")
    parser.add_argument("--random_order", action="store_true", default=False, help="Shuffle frame order")
    parser.add_argument("--epd_name", default=None, help="EPD driver name (None = auto detect)")
    parser.add_argument("--loglevel", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    args = parser.parse_args()

    # ---- 初始化日志 ----
    logging.basicConfig(level=getattr(logging, args.loglevel), format="%(levelname)s: %(message)s")
    logger = logging.getLogger("LMDBPlayer")

    # ---- 初始化 ePaper ----
    try:
        epd = displayfactory.load_display_driver(args.epd_name)
    except EPDNotFoundError:
        valid = displayfactory.list_supported_displays()
        logger.error(f"无法加载 ePaper 驱动，请检查名称。可用驱动：\n{valid}")
        sys.exit(1)

    width, height = epd.width, epd.height
    #logger.info(f"Using display: {epd.NAME} ({width}x{height})")

    # ---- 优雅退出 ----
    def graceful_exit(signum=None, frame=None):
        logger.info("Exiting ...")
        epd.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

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
                logger.error(f"无法打开 {lmdb_name}: {e}")
                continue

            with env.begin(buffers=False) as txn:
                cursor = txn.cursor()
                keys = [k for k, _ in cursor]

                if not keys:
                    logger.warning(f"{lmdb_name} is empty, skipping.")
                    continue

                if args.random_order:
                    random.shuffle(keys)

                total = len(keys)
                logger.info(f"{lmdb_name} contains {total} frames.")

                for idx, key in enumerate(keys):
                    val = txn.get(key)
                    if val is None:
                        continue
                    try:
                        img = Image.open(BytesIO(val))

                        epd.prepare()
                        epd.display(img)
                        time.sleep(args.delay)
                        epd.sleep()

                        if idx % 500 == 0:
                            logger.debug(f"Displayed {idx}/{total} frames from {lmdb_name}")

                    except Exception as e:
                        logger.warning(f"Frame {key.decode('utf-8', errors='ignore')} failed: {e}")
                        continue

            env.close()
            logger.info(f"Finished {lmdb_name}")

        if not args.loop:
            break

    logger.info("All LMDB playback complete. Exiting.")
    graceful_exit()


if __name__ == "__main__":
    main()
