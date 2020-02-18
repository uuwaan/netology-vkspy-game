import datetime as dt
import time

_ERR_EXCEED = "Number of requested tokens {0} exceeds maximum of {1}"


class TokenBucket:
    def __init__(self, tps):
        self._tps = tps
        self._prev_t = dt.datetime.now()
        self._tokens = 0

    def ok(self, tnum):
        if tnum > self._tps:
            raise ValueError(_ERR_EXCEED.format(tnum, self._tps))
        now_t = dt.datetime.now()
        if int((now_t - self._prev_t).total_seconds()) > 0:
            self._tokens = self._tps
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
