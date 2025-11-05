import datetime, logging, sys
import random, subprocess, time
import requests
from omni_epd import displayfactory, EPDNotFoundError
from toolkit.functions import *

random.seed()

# init logger
logging.basicConfig(level=getattr(logging, "INFO"), format="%(levelname)s: %(message)s")
logger = logging.getLogger("LMDBPlayer")

def get_time_period(hour: int) -> str:
    if 5 <= hour < 11:
        return "morning"
    elif 11 <= hour < 14:
        return "noon"
    elif 14 <= hour < 18:
        return "afternoon"
    else:
        return "evening"

def random_greeting(period: str) -> str:
    greetings = {
        "morning": [
            "早上好！今天也要元气满满哦～",
            "Good morning! 祝你有个愉快的一天！",
            "早安，世界正在等你发光",
            "新的一天，新的开始，加油！",
            "清晨的阳光真美，愿你今天也很顺利～"
        ],
        "noon": [
            "中午好！吃饭别太快，记得休息一下",
            "午安～补充能量继续奋斗！",
            "中午啦！吃好饭、睡好觉才有力气干活",
            "午饭时间到～今天吃点好的吧！",
            "中午好呀～工作学习都别太累喔～"
        ],
        "afternoon": [
            "下午好～注意别犯困",
            "下午啦，打起精神继续冲刺吧！",
            "午后阳光真舒服，记得伸个懒腰～",
            "希望你的下午像阳光一样温暖",
            "下午好！别忘了补水和休息一下～"
        ],
        "evening": [
            "晚上好～今天辛苦啦",
            "Good evening! 是时候放松一下了～",
            "夜色正好，放慢脚步享受片刻安宁～",
            "晚上好，来杯热茶犒劳一下自己吧",
            "辛苦一天啦，记得早点休息哦"
        ]
    }
    return random.choice(greetings[period])

def main():
    now = datetime.datetime.now()
    period = get_time_period(now.hour)
    greeting = random_greeting(period)

    cmd = [
            "/home/baoste/epaper-env/bin/python",
            "/home/baoste/epaper2xl/display_img.py",
            "--img_path", "",
            "--text", greeting
    ]
    subprocess.Popen(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True
    )
    logger.info(f"Print {greeting}")

    time.sleep(600)
    pid = search_existing_display_scripts()
    if not pid:
        url = "http://127.0.0.1/play_movie"
        requests.post(url)

if __name__ == "__main__":
    main()
