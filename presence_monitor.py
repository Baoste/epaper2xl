"""Sequential presence checks with a delay after processing and display finish."""

import logging
import math
import json
import os
import time
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
THRESHOLD = 0.38
OWNER_TEXT = "你好，一帆"
VISITOR_TEXT = "欢迎来访，请稍候～"
ABSENT_TEXT = "这里是徐一帆的工位，目前不在哦~"
REST_TEXT = "夜深人静，休息中……"
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
FIRST_TEXT = "你好，一帆！\n新的一天，顺顺利利～"
RETURN_TEXT = "欢迎回来，一帆！"
BREAK_TEXT = "一帆，休息一下吧～\n抬头远眺，活动肩膀"
GREETING_SECONDS = 60
WORK_SECONDS = 60 * 60
BREAK_SECONDS = 5 * 60
ABSENCE_CONFIRM_SECONDS = 5
HISTORY_PATH = Path(__file__).resolve().parent / ".face_cache" / "presence.json"

# Rows = states; columns = events. None means stay in the current state.
EVENTS = ("owner", "low", "low3", "no_face", "invalid", "night", "wake",
          "greeting_done", "work_due", "break_done", "absence_confirmed")
TRANSITIONS = {
    "absent":  ("arrival", None, "visitor", "absent", None, "rest", None, None, None, None, None),
    "visitor": ("arrival", None, None, "absent", None, "rest", None, None, None, None, None),
    "first":   (None, None, None, "absent", None, "rest", None, "owner", None, None, None),
    "return":  (None, None, None, "absent", None, "rest", None, "owner", None, None, None),
    "owner":   (None, None, None, None, None, "rest", None, None, "break", None, "absent"),
    "break":   (None, None, None, "absent", None, "rest", None, None, None, "owner", None),
    "rest":    (None, None, None, None, None, None, "absent", None, None, None, None),
}
STATE_TEXTS = {
    "absent": (ABSENT_TEXT, "一帆暂时不在工位～", "这里是一帆的工位\n此刻无人，欢迎稍后来访"),
    "visitor": (VISITOR_TEXT, "你好，欢迎来到一帆的工位！", "很高兴见到你\n欢迎来访～"),
    "first": (FIRST_TEXT, "一帆，今天也请多关照～", "你好，一帆！\n新的一天，从容开始"),
    "return": (RETURN_TEXT, "一帆，你回来啦～", "又见面啦，一帆！\n继续自己的节奏吧"),
    "owner": (OWNER_TEXT, "一帆，按自己的节奏来～", "一帆，手边的事慢慢做好"),
    "break": (BREAK_TEXT, "一帆，歇一小会儿\n喝口水，看看远处", "忙了一阵啦，一帆\n起身伸个懒腰吧～"),
    "rest": (REST_TEXT, "工位打烊啦\n明天再见，晚安～", "今晚先休息\n让忙碌留给明天吧"),
}


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
    def __init__(self, now=None, monotonic=None, history_path=None):
        self.now = now or local_now
        self.monotonic = monotonic or time.monotonic
        self.history_path = Path(history_path) if history_path is not None else None
        self.last_greeted_date = None
        if self.history_path is not None:
            try:
                value = json.loads(self.history_path.read_text(encoding="utf-8"))
                self.last_greeted_date = datetime.strptime(value["date"], "%Y-%m-%d").date().isoformat()
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self.low_count = 0
        self.state = "absent"
        self.displayed_at = None
        self.arrival_date = None
        self.absence_since = None
        self._text_state = None
        self._text = None

    @property
    def text(self):
        if self._text_state != self.state:
            self._text = random.choice(STATE_TEXTS[self.state])
            self._text_state = self.state
        return self._text

    def dispatch(self, event):
        target = TRANSITIONS[self.state][EVENTS.index(event)]
        if target == "arrival":
            self.arrival_date = self.now().date().isoformat()
            if self.last_greeted_date != self.arrival_date:
                target = "first"
            else:
                target = "return"
        if target is not None and target != self.state:
            self.state = target
            self.displayed_at = None
            self.absence_since = None
            self._text_state = None

    def displayed(self, text):
        """Start durations only after the requested text is successfully displayed."""
        if text != self.text or self.displayed_at is not None:
            return
        self.displayed_at = self.monotonic()
        if self.state == "first":
            self.last_greeted_date = self.arrival_date
            if self.history_path is not None:
                temporary = self.history_path.with_suffix(".tmp")
                try:
                    self.history_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary.write_text(json.dumps({"date": self.last_greeted_date}), encoding="utf-8")
                    os.replace(temporary, self.history_path)
                except OSError:
                    logger.warning("首次问候记录保存失败，仅本次运行有效", exc_info=True)

    def night(self):
        self.low_count = 0
        self.dispatch("night")
        return self.text

    def timer_remaining(self):
        duration = {"first": GREETING_SECONDS, "return": GREETING_SECONDS,
                    "owner": WORK_SECONDS, "break": BREAK_SECONDS}.get(self.state)
        if duration is None or self.displayed_at is None:
            return None
        return max(0, duration - (self.monotonic() - self.displayed_at))

    def wait_seconds(self, delay):
        if self.absence_since is not None:
            return min(delay, 1)
        remaining = self.timer_remaining()
        # If an error prevents a timed transition, retain the normal retry interval.
        return min(delay, remaining) if remaining is not None and remaining > 0 else delay

    def observe(self, result):
        self.dispatch("wake")
        status = result.get("status")
        score = result.get("similarity")
        event, delay = "invalid", 5
        if status == "no_face":
            event = "no_face"
        elif status == "ok" and isinstance(score, (int, float)) and math.isfinite(score):
            event, delay = ("owner", 60) if score >= THRESHOLD else ("low", 2)
        if event == "no_face" and self.state == "owner":
            sampled_at = self.monotonic()
            if self.absence_since is None:
                self.absence_since = sampled_at
            if sampled_at - self.absence_since > ABSENCE_CONFIRM_SECONDS:
                event = "absence_confirmed"
            else:
                delay = 1
        else:
            # Any face, invalid sample or camera failure breaks continuous absence.
            self.absence_since = None
        if event == "low" and self.state in ("absent", "visitor"):
            self.low_count = min(3, self.low_count + 1)
            if self.low_count == 3:
                event = "low3"
        else:
            self.low_count = 0
        self.dispatch(event)
        # Absence takes priority over expired greetings/reminders in the same sample.
        if event in ("owner", "low", "low3") and self.timer_remaining() == 0:
            timer_event = {"first": "greeting_done", "return": "greeting_done",
                           "owner": "work_due", "break": "break_done"}.get(self.state)
            if timer_event:
                self.dispatch(timer_event)
        if self.state == "break":
            delay = min(delay, 5)
        text = self.text
        if event == "invalid" or (event in ("low", "low3") and self.state == "absent"):
            text = None
        return self.wait_seconds(delay), text


def run_monitor(capture, display, stop, pause_camera=None, now=None):
    now = now or local_now
    policy = PresencePolicy(now=now, history_path=HISTORY_PATH)
    last_report = None
    while not stop.is_set():
        delay = 5
        try:
            if is_rest_time(now()):
                text = policy.night()
                if pause_camera is not None:
                    pause_camera()
                if display(text) is True:
                    policy.displayed(text)
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
            report = (policy.state, result.get("status"), delay, text, policy.low_count)
            if report != last_report:
                logger.info("工位状态 %s：%s，连续低分 %d 次，本轮完成后等待 %.1fs；%s",
                            policy.state, result.get("status"), policy.low_count, delay, result.get("message", ""))
                last_report = report
            if text is not None:
                if display(text) is True:
                    policy.displayed(text)
            if is_rest_time(now()):
                continue
        except Exception:
            policy.low_count = 0
            policy.absence_since = None
            delay = 5
            logger.exception("工位检测异常，5 秒后重试")
        # Never subtract processing time or schedule another inference concurrently.
        # Cap the wait so a 60-second daytime interval cannot run past 22:00.
        if stop.wait(min(policy.wait_seconds(delay), seconds_to_boundary(now()))):
            break
