import axios from "axios";
import {apiClient} from "@/api/api";
import {ChatApiError, parseErrorDetail, type ErrorDetail} from "@/api/errors";
import {SSEParser} from "@/lib/sse";

export interface ChatSessionSummary {
    id: string;
    /** Backend fills from the first user message; may be absent on older sessions. */
    title?: string;
    /** Preview of the last message — display fallback when title is empty. */
    last_message?: string | null;
    created_at: string;
}

export interface ChatMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    created_at?: string;
}

export interface ChatSession extends ChatSessionSummary {
    messages: ChatMessage[];
}

export interface Credits {
    searches_left: number;
    scans_left: number;
}

export interface UsageEvent {
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    session_tokens_total: number;
}

export type CappedReason = "token_cap" | "daily_budget";

export interface DoneEvent {
    session_id: string;
    message_id: string;
    capped: boolean;
}

export interface StreamCallbacks {
    onToken?: (text: string) => void;
    /** Intermediate agent reasoning between tool calls ("Ход поиска"). */
    onStep?: (text: string) => void;
    onUsage?: (usage: UsageEvent) => void;
    onCapped?: (reason: CappedReason) => void;
    onDone?: (done: DoneEvent) => void;
    onError?: (message: string) => void;
}

export interface StreamResult {
    /** True when the stream ended with a `done` or `error` event, false on connection loss. */
    finished: boolean;
}

export const createSession = async (title?: string): Promise<ChatSessionSummary> =>
    (await apiClient.post("/chat/sessions", title ? {title} : {})).data;

export const listSessions = async (): Promise<ChatSessionSummary[]> => {
    const data = (await apiClient.get("/chat/sessions")).data;
    return Array.isArray(data) ? data : (data.items ?? []);
};

export const getSession = async (sessionId: string): Promise<ChatSession> =>
    (await apiClient.get(`/chat/sessions/${sessionId}`)).data;

export const getCredits = async (): Promise<Credits> =>
    (await apiClient.get("/credits")).data;

export interface ScanMetadata {
    doc_type: string;
    names: string[];
    dates: string[];
    place: string;
}

export interface ScanUploadResult {
    scan_id: number;
    status: "done" | "error";
    extracted_text: string;
    metadata: ScanMetadata;
    model_used: string;
    watermarked: boolean;
}

export type ScanUploadErrorCode = "no_scans_left" | "too_large" | "unsupported_type" | "unknown";

export class ScanUploadError extends Error {
    constructor(
        public readonly code: ScanUploadErrorCode,
        message: string,
    ) {
        super(message);
        this.name = "ScanUploadError";
    }
}

export const uploadScan = async (sessionId: string, file: File): Promise<ScanUploadResult> => {
    const formData = new FormData();
    formData.append("file", file);
    try {
        return (await apiClient.post(`/chat/sessions/${sessionId}/scans`, formData)).data;
    } catch (error) {
        if (axios.isAxiosError(error) && error.response) {
            const status = error.response.status;
            if (status === 402) {
                throw new ScanUploadError("no_scans_left", "Сканы закончились");
            }
            if (status === 413) {
                throw new ScanUploadError("too_large", "Файл больше 10 МБ — сожмите или обрежьте скан");
            }
            if (status === 415) {
                throw new ScanUploadError("unsupported_type", "Поддерживаются только JPEG, PNG и TIFF");
            }
        }
        throw new ScanUploadError("unknown", "Не удалось обработать скан. Попробуйте ещё раз.");
    }
};

export async function streamMessage(
    sessionId: string,
    content: string,
    callbacks: StreamCallbacks,
    signal?: AbortSignal,
    scanIds?: number[],
): Promise<StreamResult> {
    const token = localStorage.getItem("token");
    const response = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(token ? {Authorization: `Bearer ${token}`} : {}),
        },
        body: JSON.stringify(scanIds && scanIds.length > 0 ? {content, scan_ids: scanIds} : {content}),
        signal,
    });

    if (response.status === 401) {
        localStorage.removeItem("token");
        window.dispatchEvent(new CustomEvent("auth:expired"));
        throw new Error("Требуется повторный вход");
    }
    if (!response.ok || !response.body) {
        let detail: ErrorDetail = {code: null, message: null};
        try {
            detail = parseErrorDetail((await response.json())?.detail);
        } catch {
            // body wasn't JSON — keep the null detail
        }
        throw new ChatApiError(
            detail.code,
            detail.message ?? `Сервер вернул ошибку ${response.status}`,
        );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const parser = new SSEParser();
    let doneReceived = false;
    let errorReceived = false;

    const dispatch = (event: string, raw: string) => {
        let payload: unknown;
        try {
            payload = JSON.parse(raw);
        } catch {
            return;
        }
        switch (event) {
            case "token":
                callbacks.onToken?.((payload as { text: string }).text);
                break;
            case "step":
                callbacks.onStep?.((payload as { text: string }).text);
                break;
            case "usage":
                callbacks.onUsage?.(payload as UsageEvent);
                break;
            case "capped":
                callbacks.onCapped?.((payload as { reason: CappedReason }).reason);
                break;
            case "done":
                doneReceived = true;
                callbacks.onDone?.(payload as DoneEvent);
                break;
            case "error":
                errorReceived = true;
                callbacks.onError?.((payload as { message: string }).message);
                break;
        }
    };

    try {
        for (;;) {
            const {done, value} = await reader.read();
            if (done) break;
            for (const ev of parser.feed(decoder.decode(value, {stream: true}))) {
                dispatch(ev.event, ev.data);
            }
        }
        for (const ev of parser.flush()) {
            dispatch(ev.event, ev.data);
        }
    } finally {
        reader.releaseLock();
    }

    return {finished: doneReceived || errorReceived};
}
