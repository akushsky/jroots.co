import logging
import time
import uuid
from urllib.parse import unquote

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import AsyncSessionLocal
from app.middleware.trace import trace_id_ctx_var
from app.services.auth import resolve_user_from_token

logger = logging.getLogger("jroots")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        trace_id_ctx_var.set(trace_id)

        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None

        async with AsyncSessionLocal() as db:
            user = await resolve_user_from_token(token, db)

        response = await call_next(request)

        duration = time.time() - start_time
        query_params = str(request.query_params)

        logger.info(
            "%s %s%s User: %s Status: %d Duration: %.3fs",
            request.method,
            request.url.path,
            f"?{unquote(query_params)}" if query_params else "",
            user.email if user else "Anonymous",
            response.status_code,
            duration,
        )

        response.headers["X-Request-ID"] = trace_id
        return response
