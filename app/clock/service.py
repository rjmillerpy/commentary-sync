"""The server's clock: the one timeline every device's audio is placed on.

A phone or laptop clock can be seconds off. Sync compares audio recorded on
two devices, so each client measures how far its clock is from this one
(halfway through a request to GET /clock is when the server read it) and
stamps what it records in server time.
"""

import time
from collections.abc import Callable

from app.clock.schema import ServerTime


def server_time(clock: Callable[[], float] = time.time) -> ServerTime:
    return ServerTime(now=clock())
