import {afterEach, describe, expect, it, vi} from "vitest";
import {streamMessage} from "../chat";
import type {StreamCallbacks} from "../chat";

function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    return new ReadableStream({
        start(controller) {
            for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
            controller.close();
        },
    });
}

function mockFetchSSEResponse(chunks: string[]) {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            new Response(sseStream(chunks), {
                status: 200,
                headers: {"Content-Type": "text/event-stream"},
            }),
        ),
    );
}

function makeCallbacks() {
    return {
        onToken: vi.fn(),
        onUsage: vi.fn(),
        onCapped: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
    } satisfies StreamCallbacks;
}

describe("streamMessage", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        localStorage.clear();
    });

    it("posts with SSE accept header and bearer token", async () => {
        localStorage.setItem("token", "jwt-123");
        mockFetchSSEResponse(['event: done\ndata: {"session_id":"s1","message_id":"m1","capped":false}\n\n']);

        await streamMessage("s1", "привет", makeCallbacks());

        expect(fetch).toHaveBeenCalledWith(
            "/api/chat/sessions/s1/messages",
            expect.objectContaining({
                method: "POST",
                body: JSON.stringify({content: "привет"}),
                headers: expect.objectContaining({
                    Accept: "text/event-stream",
                    Authorization: "Bearer jwt-123",
                }),
            }),
        );
    });

    it("dispatches token, usage, capped and done events across chunk boundaries", async () => {
        const callbacks = makeCallbacks();
        mockFetchSSEResponse([
            'event: token\ndata: {"text":"На',
            'чните"}\n\nevent: token\ndata: {"text":" с ревизий"}\n\n',
            'event: usage\ndata: {"model":"m","prompt_tokens":1,"completion_tokens":2,"session_tokens_total":3}\n\n',
            'event: capped\ndata: {"reason":"token_cap"}\n\n',
            'event: done\ndata: {"session_id":"s1","message_id":"m9","capped":true}\n\n',
        ]);

        const result = await streamMessage("s1", "x", callbacks);

        expect(result.finished).toBe(true);
        expect(callbacks.onToken).toHaveBeenNthCalledWith(1, "Начните");
        expect(callbacks.onToken).toHaveBeenNthCalledWith(2, " с ревизий");
        expect(callbacks.onUsage).toHaveBeenCalledWith({
            model: "m",
            prompt_tokens: 1,
            completion_tokens: 2,
            session_tokens_total: 3,
        });
        expect(callbacks.onCapped).toHaveBeenCalledWith("token_cap");
        expect(callbacks.onDone).toHaveBeenCalledWith({
            session_id: "s1",
            message_id: "m9",
            capped: true,
        });
    });

    it("marks stream finished on server error event and reports the message", async () => {
        const callbacks = makeCallbacks();
        mockFetchSSEResponse(['event: error\ndata: {"message":"модель недоступна"}\n\n']);

        const result = await streamMessage("s1", "x", callbacks);

        expect(result.finished).toBe(true);
        expect(callbacks.onError).toHaveBeenCalledWith("модель недоступна");
    });

    it("returns finished=false when the connection drops mid-stream", async () => {
        const callbacks = makeCallbacks();
        mockFetchSSEResponse(['event: token\ndata: {"text":"половина"}\n\n', 'event: token\ndata: {"text":"оборва']);

        const result = await streamMessage("s1", "x", callbacks);

        expect(result.finished).toBe(false);
        // complete token delivered, truncated trailing JSON discarded
        expect(callbacks.onToken).toHaveBeenCalledTimes(1);
        expect(callbacks.onToken).toHaveBeenCalledWith("половина");
        expect(callbacks.onDone).not.toHaveBeenCalled();
    });

    it("throws and clears the token on 401", async () => {
        localStorage.setItem("token", "expired");
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, {status: 401})));

        await expect(streamMessage("s1", "x", makeCallbacks())).rejects.toThrow();
        expect(localStorage.getItem("token")).toBeNull();
    });
});
