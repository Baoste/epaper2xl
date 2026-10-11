"""Sequential presence checks with a delay after processing and display finish."""

import logging
import math
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
THRESHOLD = 0.38
OWNER_TEXT = "你好，一帆"
VISITOR_TEXT = "欢迎来访，请稍候～"
ABSENT_TEXT = "这里是徐一帆的工位，目前不在哦~"
REST_TEXT = "夜深人静，休息中……"
LOCAL_TIMEZONE = timezone(timedelta(hours=8))


def local_now():
    return datetime.now(LOCAL_TIMEZONE)


def is_rest_time(now=None):
    now = now if now is not None else local_now()
    return now.hour >= 22 or now.hour < 8


def seconds_to_boundary(now):
    if now.hour < 8:
        boundary = now.replace(hour=8, minute=0, second=0, microsecond=0)
    elif now.hour < 22:
        boundary = now.replace(hour=22, minute=0, second=0, microsecond=0)
    else:
        boundary = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    return (boundary - now).total_seconds()


class PresencePolicy:
    def __init__(self):
        self.low_count = 0

    def observe(self, result):
        status = result.get("status")
        if status == "ok":
            score = result.get("similarity")
            if isinstance(score, (int, float)) and math.isfinite(score):
                if score >= THRESHOLD:
                    self.low_count = 0
                    return 60, OWNER_TEXT
                self.low_count = min(3, self.low_count + 1)
                return 2, VISITOR_TEXT if self.low_count == 3 else None
        self.low_count = 0
        if status == "no_face":
            return 5, ABSENT_TEXT
        # Multiple faces / camera or model errors are not evidence of absence.
        return 5, None


def run_monitor(capture, display, stop, pause_camera=None, now=None):
    now = now or local_now
    policy = PresencePolicy()
    last_report = None
    while not stop.is_set():
        delay = 5
        try:
            if is_rest_time(now()):
                policy.low_count = 0
                if pause_camera is not None:
                    pause_camera()
                display(REST_TEXT)
                if last_report != "rest":
                    logger.info("进入夜间休息，08:00 恢复检测（UTC+8）")
                    last_report = "rest"
                if not is_rest_time(now()):
                    continue
                if stop.wait(min(60, seconds_to_boundary(now()))):
                    break
                continue
            result = capture()
            if stop.is_set():
                break
            if is_rest_time(now()):
                # Discard a daytime result that finished after 22:00.
                continue
            delay, text = policy.observe(result)
            report = (result.get("status"), delay, text, policy.low_count)
            if report != last_report:
                logger.info("工位检测：%s，连续低分 %d 次，本轮完成后等待 %ds；%s",
                            result.get("status"), policy.low_count, delay, result.get("message", ""))
                last_report = report
            if text is not None:
                display(text)
            if is_rest_time(now()):
                continue
        except Exception:
            policy.low_count = 0
            delay = 5
            logger.exception("工位检测异常，5 秒后重试")
        # Never subtract processing time or schedule another inference concurrently.
        # Cap the wait so a 60-second daytime interval cannot run past 22:00.
        if stop.wait(min(delay, seconds_to_boundary(now()))):
            break
