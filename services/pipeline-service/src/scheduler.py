from __future__ import annotations

import logging
import time
from collections.abc import Callable

LOG = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, interval_seconds: int, name: str, job: Callable[[], None]) -> None:
        self.interval_seconds = max(1, interval_seconds)
        self.name = name
        self.job = job

    def run_forever(self) -> None:
        LOG.info("scheduler %s started interval=%ss", self.name, self.interval_seconds)
        while True:
            started = time.time()
            try:
                self.job()
            except Exception:
                LOG.exception("scheduler %s job failed", self.name)
            elapsed = time.time() - started
            sleep_for = max(1, self.interval_seconds - int(elapsed))
            time.sleep(sleep_for)
