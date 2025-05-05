from contextvars import ContextVar

trace_id_ctx_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    return trace_id_ctx_var.get()
