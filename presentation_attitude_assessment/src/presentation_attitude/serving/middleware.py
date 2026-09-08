"""HTTP request limits, independent of job storage and analysis."""

from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartException


class UploadLimit:
    """Bound the entire multipart body before it can fill temporary storage."""

    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(
                scope, receive, send
            )
        if length > self.limit:
            return await JSONResponse({"detail": "Upload exceeds request limit"}, 413)(
                scope, receive, send
            )
        received, exceeded = 0, False

        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.limit:
                exceeded = True
                # Starlette closes partially spooled files for MultiPartException.
                raise MultiPartException("Upload exceeds request limit")
            return message

        async def bounded_send(message):
            if exceeded and message["type"] == "http.response.start":
                message = {**message, "status": 413}
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)
