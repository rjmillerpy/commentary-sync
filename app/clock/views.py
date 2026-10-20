"""HTTP endpoint for the clock.

GET /clock   the server's time, for clients to correct their own clocks by
"""

from fastapi import APIRouter, Response

from app.clock import service
from app.clock.schema import ServerTime
from app.common.http_headers import CACHE_CONTROL_HEADER, NO_STORE

clock_router = APIRouter(tags=["clock"])


@clock_router.get("")
async def server_time(response: Response) -> ServerTime:
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # a cached time is a wrong time
    return service.server_time()
