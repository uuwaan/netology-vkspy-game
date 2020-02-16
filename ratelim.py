import datetime as dt
import time


class TokenBucket:
    def __init__(self, tps, burst):
        self._tps = tps
        self._burst = burst
        self._prev_t = dt.datetime.now()
        self._tokens = 0

    def ok(self, tnum):
        now_t = dt.datetime.now()
        delta_secs = int((now_t - self._prev_t).total_seconds())
        self._tokens += min(delta_secs * self._tps, self._burst)
        if self._tokens < tnum:
            return False
        else:
            self._tokens -= tnum
            self._prev_t = now_t
            return True

    def wait(self, tnum):
        delay = tnum / self._tps
        while not self.ok(tnum):
            time.sleep(delay)
