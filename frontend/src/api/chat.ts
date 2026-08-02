import {apiClient} from "@/api/api";
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

export async function streamMessage(
    sessionId: string,
    content: string,
    callbacks: StreamCallbacks,
    signal?: AbortSignal,
): Promise<StreamResult> {
    const token = localStorage.getItem("token");
    const response = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(token ? {Authorization: `Bearer ${token}`} : {}),
        },
        body: JSON.stringify({content}),
        signal,
    });

    if (response.status === 401) {
        localStorage.removeItem("token");
        window.dispatchEvent(new CustomEvent("auth:expired"));
        throw new Error("Требуется повторный вход");
    }
    if (!response.ok || !response.body) {
        throw new Error(`Сервер вернул ошибку ${response.status}`);
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
