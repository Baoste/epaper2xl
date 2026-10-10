"""Sequential presence checks with a delay after processing and display finish."""

import logging
import math

logger = logging.getLogger(__name__)
THRESHOLD = 0.38
OWNER_TEXT = "你好，一帆"
VISITOR_TEXT = "欢迎来访，请稍候～"
ABSENT_TEXT = "这里是徐一帆的工位，目前不在哦~"


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
                return 1, VISITOR_TEXT if self.low_count == 3 else None
        self.low_count = 0
        if status == "no_face":
            return 5, ABSENT_TEXT
        # Multiple faces / camera or model errors are not evidence of absence.
        return 5, None


def run_monitor(capture, display, stop):
    policy = PresencePolicy()
    last_report = None
    while not stop.is_set():
        delay = 5
        try:
            result = capture()
            if stop.is_set():
                break
            delay, text = policy.observe(result)
            report = (result.get("status"), delay, text, policy.low_count)
            if report != last_report:
                logger.info("工位检测：%s，连续低分 %d 次，本轮完成后等待 %ds；%s",
                            result.get("status"), policy.low_count, delay, result.get("message", ""))
                last_report = report
            if text is not None:
                display(text)
        except Exception:
            policy.low_count = 0
            logger.exception("工位检测异常，5 秒后重试")
        # Never subtract processing time or schedule another inference concurrently.
        if stop.wait(delay):
            break
