import time
import uuid
from urllib.parse import unquote

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from crud import resolve_user_from_token
from database import AsyncSessionLocal
from logging_config import construct_logger
from trace_context import trace_id_ctx_var

logger = construct_logger("jroots")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Extract or generate trace ID
        trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        trace_id_ctx_var.set(trace_id)

        # Extract Bearer token manually
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None

        # Manually create DB session (no DI in middleware!)
        async with AsyncSessionLocal() as db:
            user = await resolve_user_from_token(token, db)

        response = await call_next(request)

        duration = time.time() - start_time
        query_params = str(request.query_params)

        logger.info(
            f"{request.method} {request.url.path}"
            f"{'?' + unquote(query_params) if query_params else ''} "
            f"User: {user.email if user else 'Anonymous'} "
            f"Status: {response.status_code} "
            f"Duration: {duration:.3f}s"
        )

        # Optionally, add the trace ID to the response headers
        response.headers["X-Request-ID"] = trace_id

        return response
