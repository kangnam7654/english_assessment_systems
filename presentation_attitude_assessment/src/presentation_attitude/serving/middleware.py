"""HTTP request limits, independent of job storage and analysis."""

from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartException


class UploadLimit:
    """Bound the entire multipart body before it can fill temporary storage."""

    def __init__(self, app, limit):
        """Wrap an ASGI app with a maximum request-body size.

        Args:
            app: ASGI application or FastAPI instance whose lifecycle is being configured.
            limit: Maximum allowed request-body size in bytes.
        """
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        """Enforce upload limits while forwarding ASGI request and response messages.

        Args:
            scope: ASGI connection scope.
            receive: ASGI callable receiving incoming messages.
            send: ASGI callable sending outgoing messages.

        Returns:
            Result of the delegated ASGI call on early-return branches; otherwise None.
        """
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
            """Count received body bytes and abort a request that exceeds the limit.

            Returns:
                Incoming ASGI message when the cumulative body size remains within the limit.
            """
            nonlocal received, exceeded
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.limit:
                exceeded = True
                # Starlette closes partially spooled files for MultiPartException.
                raise MultiPartException("Upload exceeds request limit")
            return message

        async def bounded_send(message):
            """Rewrite the outgoing status to HTTP 413 after an upload limit violation.

            Args:
                message: ASGI message to forward.
            """
            if exceeded and message["type"] == "http.response.start":
                message = {**message, "status": 413}
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)
