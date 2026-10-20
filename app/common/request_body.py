"""Reading a raw request body without letting a client send unlimited bytes."""

from http import HTTPStatus

from fastapi import HTTPException, Request

TOO_LARGE_DETAIL = "Request body too large"


async def read_limited_body(request: Request, limit: int) -> bytes:
    """The request body, refused with 413 once it passes `limit` bytes,
    without reading the rest into memory."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, TOO_LARGE_DETAIL)
    return bytes(body)
