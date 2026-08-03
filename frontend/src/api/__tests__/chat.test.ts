import {afterEach, describe, expect, it, vi} from "vitest";
import {streamMessage, uploadScan, ScanUploadError} from "../chat";
import type {StreamCallbacks, ScanUploadResult} from "../chat";
import {apiClient} from "@/api/api";

vi.mock("@/api/api", () => ({
    apiClient: {
        post: vi.fn(),
    },
}));

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
        onStep: vi.fn(),
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

    it("dispatches step events to onStep, separate from tokens", async () => {
        const callbacks = makeCallbacks();
        mockFetchSSEResponse([
            'event: step\ndata: {"text":"Ищу в ревизских сказках…"}\n\n',
            'event: token\ndata: {"text":"Ответ"}\n\n',
            'event: step\ndata: {"text":"Проверяю метрики…"}\n\n',
            'event: done\ndata: {"session_id":"s1","message_id":"m2","capped":false}\n\n',
        ]);

        const result = await streamMessage("s1", "x", callbacks);

        expect(result.finished).toBe(true);
        expect(callbacks.onStep).toHaveBeenNthCalledWith(1, "Ищу в ревизских сказках…");
        expect(callbacks.onStep).toHaveBeenNthCalledWith(2, "Проверяю метрики…");
        expect(callbacks.onToken).toHaveBeenCalledTimes(1);
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

    it("includes scan_ids in the message body when provided", async () => {
        mockFetchSSEResponse(['event: done\ndata: {"session_id":"s1","message_id":"m1","capped":false}\n\n']);

        await streamMessage("s1", "привет", makeCallbacks(), undefined, [3, 7]);

        expect(fetch).toHaveBeenCalledWith(
            "/api/chat/sessions/s1/messages",
            expect.objectContaining({
                body: JSON.stringify({content: "привет", scan_ids: [3, 7]}),
            }),
        );
    });
});

function axiosError(status: number) {
    const error = new Error(`Request failed with status code ${status}`);
    Object.assign(error, {isAxiosError: true, response: {status, data: {}}});
    return error;
}

describe("uploadScan", () => {
    afterEach(() => {
        vi.clearAllMocks();
    });

    const scanResult: ScanUploadResult = {
        scan_id: 7,
        status: "done",
        extracted_text: "текст",
        metadata: {doc_type: "metric_book", names: [], dates: [], place: ""},
        model_used: "ocr",
        watermarked: false,
    };

    it("posts the file as multipart form data and returns the result", async () => {
        vi.mocked(apiClient.post).mockResolvedValue({data: scanResult});
        const file = new File(["scan"], "metrika.jpg", {type: "image/jpeg"});

        const result = await uploadScan("s1", file);

        expect(result).toEqual(scanResult);
        expect(apiClient.post).toHaveBeenCalledWith(
            "/chat/sessions/s1/scans",
            expect.any(FormData),
        );
        const formData = vi.mocked(apiClient.post).mock.calls[0][1] as FormData;
        expect(formData.get("file")).toBe(file);
    });

    it("maps 402 to no_scans_left", async () => {
        vi.mocked(apiClient.post).mockRejectedValue(axiosError(402));

        const error = await uploadScan("s1", new File(["x"], "a.jpg")).catch((e) => e);
        expect(error).toBeInstanceOf(ScanUploadError);
        expect((error as ScanUploadError).code).toBe("no_scans_left");
    });

    it("maps 413 to too_large and 415 to unsupported_type", async () => {
        vi.mocked(apiClient.post).mockRejectedValue(axiosError(413));
        let error = await uploadScan("s1", new File(["x"], "a.jpg")).catch((e) => e);
        expect((error as ScanUploadError).code).toBe("too_large");

        vi.mocked(apiClient.post).mockRejectedValue(axiosError(415));
        error = await uploadScan("s1", new File(["x"], "a.jpg")).catch((e) => e);
        expect((error as ScanUploadError).code).toBe("unsupported_type");
    });

    it("maps any other failure to unknown", async () => {
        vi.mocked(apiClient.post).mockRejectedValue(axiosError(500));
        let error = await uploadScan("s1", new File(["x"], "a.jpg")).catch((e) => e);
        expect((error as ScanUploadError).code).toBe("unknown");

        vi.mocked(apiClient.post).mockRejectedValue(new Error("network down"));
        error = await uploadScan("s1", new File(["x"], "a.jpg")).catch((e) => e);
        expect((error as ScanUploadError).code).toBe("unknown");
    });
});
