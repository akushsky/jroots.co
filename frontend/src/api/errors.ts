export interface ErrorDetail {
    code: string | null;
    message: string | null;
}

/**
 * Backend sends `detail` either as a legacy plain string or as
 * {code, message}. Normalize both into a single shape.
 */
export function parseErrorDetail(detail: unknown): ErrorDetail {
    if (typeof detail === "string") {
        return {code: null, message: detail || null};
    }
    if (detail && typeof detail === "object") {
        const record = detail as Record<string, unknown>;
        return {
            code: typeof record.code === "string" ? record.code : null,
            message: typeof record.message === "string" ? record.message : null,
        };
    }
    return {code: null, message: null};
}

/** Duck-typed extraction of `response.data.detail` from an axios-style error. */
export function axiosErrorDetail(err: unknown): ErrorDetail {
    const response = (err as { response?: { data?: { detail?: unknown } } } | null)?.response;
    return parseErrorDetail(response?.data?.detail);
}

/** HTTP error from the chat API carrying a machine-readable backend code. */
export class ChatApiError extends Error {
    readonly code: string | null;

    constructor(code: string | null, message: string) {
        super(message);
        this.name = "ChatApiError";
        this.code = code;
    }
}
