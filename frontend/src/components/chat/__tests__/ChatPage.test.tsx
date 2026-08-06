import {beforeEach, describe, expect, it, vi} from "vitest";
import {act, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter} from "react-router-dom";
import ChatPage from "../ChatPage";
import {createSession, getCredits, getSession, listSessions, streamMessage, uploadScan, ScanUploadError} from "@/api/chat";
import type {StreamCallbacks, ScanUploadResult} from "@/api/chat";
import {ChatApiError} from "@/api/errors";

vi.mock("@/api/chat", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/api/chat")>();
    return {
        createSession: vi.fn(),
        listSessions: vi.fn(),
        getSession: vi.fn(),
        getCredits: vi.fn(),
        streamMessage: vi.fn(),
        uploadScan: vi.fn(),
        ScanUploadError: actual.ScanUploadError,
    };
});

const sessionSummary = {
    id: "s1",
    title: "Ивановы из Одессы",
    created_at: "2026-08-01T10:00:00Z",
};

const scanDone: ScanUploadResult = {
    scan_id: 7,
    status: "done",
    extracted_text: "Родился Иван…",
    metadata: {doc_type: "metric_book", names: ["Иван"], dates: ["1881"], place: "Одесса"},
    model_used: "test-ocr",
    watermarked: false,
};

function renderChat() {
    return render(
        <MemoryRouter>
            <ChatPage />
        </MemoryRouter>,
    );
}

describe("ChatPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listSessions).mockResolvedValue([sessionSummary]);
        vi.mocked(getSession).mockResolvedValue({
            ...sessionSummary,
            messages: [
                {id: "m1", role: "user", content: "Ищу Ивановых из Одессы"},
                {id: "m2", role: "assistant", content: "Начните с ревизских сказок"},
            ],
        });
        vi.mocked(getCredits).mockResolvedValue({searches_left: 3, scans_left: 5});
        vi.mocked(streamMessage).mockImplementation(
            async (sessionId: string, _content: string, callbacks: StreamCallbacks) => {
                callbacks.onToken?.("Начните");
                callbacks.onToken?.(" с метрических книг Одессы.");
                callbacks.onUsage?.({
                    model: "test-model",
                    prompt_tokens: 10,
                    completion_tokens: 20,
                    session_tokens_total: 30,
                });
                callbacks.onDone?.({session_id: sessionId, message_id: "m3", capped: false});
                return {finished: true};
            },
        );
    });

    it("renders sessions, history and credits, then streams a reply", async () => {
        const user = userEvent.setup();
        renderChat();

        expect(await screen.findByText("Ивановы из Одессы")).toBeInTheDocument();
        expect(await screen.findByText("Начните с ревизских сказок")).toBeInTheDocument();
        expect(screen.getByText(/Осталось поисков: 3/)).toBeInTheDocument();

        // cross-link to the pro search lives in the footer
        expect(
            screen.getByRole("link", {name: /Профессиональный поиск/}),
        ).toHaveAttribute("href", "/");

        const input = screen.getByLabelText("Сообщение ассистенту");
        await user.type(input, "А какие годы охватывают?{Enter}");

        await waitFor(() =>
            expect(streamMessage).toHaveBeenCalledWith(
                "s1",
                "А какие годы охватывают?",
                expect.anything(),
                expect.anything(),
            ),
        );

        expect(await screen.findByText(/с метрических книг Одессы/)).toBeInTheDocument();
        expect(screen.getByText(/Токенов в сессии: 30/)).toBeInTheDocument();
    });

    it("accumulates step events as separate list items, collapsed after done", async () => {
        const user = userEvent.setup();
        let finish: (() => void) | undefined;
        vi.mocked(streamMessage).mockImplementation(
            async (sessionId: string, _content: string, callbacks: StreamCallbacks) => {
                callbacks.onStep?.("Смотрю ревизии…");
                callbacks.onStep?.("Нашёл совпадение…");
                callbacks.onToken?.("Готовый ответ.");
                await new Promise<void>((resolve) => {
                    finish = () => {
                        callbacks.onDone?.({session_id: sessionId, message_id: "m9", capped: false});
                        resolve();
                    };
                });
                return {finished: true};
            },
        );

        const {container} = renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Привет{Enter}");

        // while streaming: accordion is open, each step is its own list item
        await screen.findByText("Смотрю ревизии…");
        const items = container.querySelectorAll('[data-testid="steps-block"] li');
        expect(items).toHaveLength(2);
        expect(items[0]).toHaveTextContent("Смотрю ревизии…");
        expect(items[1]).toHaveTextContent("Нашёл совпадение…");
        // no glued text anywhere
        expect(screen.queryByText("Смотрю ревизии…Нашёл совпадение…")).not.toBeInTheDocument();

        act(() => finish?.());
        // after done: accordion collapses, the answer stays
        await waitFor(() =>
            expect(screen.queryByText("Смотрю ревизии…")).not.toBeInTheDocument(),
        );
        expect(screen.getByText("Ход поиска")).toBeInTheDocument();
        expect(screen.getByText("Готовый ответ.")).toBeInTheDocument();
    });

    it("parses <steps> blocks from persisted history into the accordion", async () => {
        vi.mocked(getSession).mockResolvedValue({
            ...sessionSummary,
            messages: [
                {id: "m1", role: "user", content: "Вопрос"},
                {id: "m2", role: "assistant", content: "<steps>Искал в архиве</steps>Чистый ответ."},
            ],
        });

        renderChat();

        expect(await screen.findByText("Чистый ответ.")).toBeInTheDocument();
        expect(screen.getByText("Ход поиска")).toBeInTheDocument();
        // collapsed by default for historical messages
        expect(screen.queryByText("Искал в архиве")).not.toBeInTheDocument();
    });

    it("strips <searchlog> from persisted answers into the accordion's «Проверенные базы»", async () => {
        const user = userEvent.setup();
        vi.mocked(getSession).mockResolvedValue({
            ...sessionSummary,
            messages: [
                {id: "m1", role: "user", content: "Вопрос"},
                {
                    id: "m2",
                    role: "assistant",
                    content:
                        "Ответ с находкой.<searchlog>\nsearch(toldot_cemetery, Клебанов Мордух) → 1 результатов\nsearch(yandex_archive, Клебанов) → 0 результатов\n</searchlog>",
                },
            ],
        });

        const {container} = renderChat();

        expect(await screen.findByText("Ответ с находкой.")).toBeInTheDocument();
        // raw journal never reaches the DOM
        expect(container.innerHTML).not.toContain("searchlog");
        expect(screen.queryByText(/toldot_cemetery/)).not.toBeInTheDocument();

        // open the accordion — the journal lines are there
        await user.click(screen.getByText("Ход поиска"));
        expect(await screen.findByText("Проверенные базы")).toBeInTheDocument();
        expect(
            screen.getByText("search(toldot_cemetery, Клебанов Мордух) → 1 результатов"),
        ).toBeInTheDocument();
        expect(
            screen.getByText("search(yandex_archive, Клебанов) → 0 результатов"),
        ).toBeInTheDocument();
    });

    it("creates a session on first send when none is active", async () => {
        const user = userEvent.setup();
        vi.mocked(listSessions).mockResolvedValue([]);
        // backend returns a fresh session without a title yet
        vi.mocked(createSession).mockResolvedValue({
            id: "s-new",
            created_at: "2026-08-02T09:00:00Z",
        });

        renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Штерн из Кишинёва{Enter}");

        await waitFor(() => expect(createSession).toHaveBeenCalled());
        await waitFor(() =>
            expect(streamMessage).toHaveBeenCalledWith(
                "s-new",
                "Штерн из Кишинёва",
                expect.anything(),
                expect.anything(),
            ),
        );

        // sidebar shows the first message as the session title optimistically —
        // one match is the user bubble, the other is the sidebar entry
        await waitFor(() =>
            expect(screen.getAllByText("Штерн из Кишинёва").length).toBeGreaterThanOrEqual(2),
        );
    });

    it("opens the tariffs modal when a lock chip in an answer is clicked", async () => {
        const user = userEvent.setup();
        vi.mocked(getSession).mockResolvedValue({
            ...sessionSummary,
            messages: [
                {id: "m1", role: "user", content: "Есть ссылки?"},
                {id: "m2", role: "assistant", content: "Запись найдена: 🔒 _доступно в полной версии_"},
            ],
        });

        renderChat();

        // balance is 3 > 0 — footer paywall is not shown, input is available
        expect(await screen.findByLabelText("Сообщение ассистенту")).toBeInTheDocument();

        await user.click(await screen.findByRole("button", {name: /в полной версии/}));

        const dialog = await screen.findByRole("dialog", {name: "Тарифы"});
        expect(dialog).toBeInTheDocument();
        expect(screen.getByText("Полная версия записи")).toBeInTheDocument();
        expect(screen.getByText(/«Дело»/)).toBeInTheDocument();
        expect(screen.getByText("$25")).toBeInTheDocument();

        await user.click(screen.getByRole("button", {name: "Закрыть"}));
        expect(screen.queryByRole("dialog", {name: "Тарифы"})).not.toBeInTheDocument();
    });

    it("shows paywall instead of input when searches are exhausted", async () => {
        vi.mocked(getCredits).mockResolvedValue({searches_left: 0, scans_left: 0});
        renderChat();

        expect(await screen.findByText("Бесплатные поиски закончились")).toBeInTheDocument();
        expect(screen.getByText(/«Дело»/)).toBeInTheDocument();
        expect(screen.getByText("$25")).toBeInTheDocument();
        expect(screen.getByText(/«Исследователь»/)).toBeInTheDocument();
        expect(screen.getByText("$15/мес")).toBeInTheDocument();
        for (const button of screen.getAllByRole("button", {name: "Оформить"})) {
            expect(button).toBeEnabled();
        }
        expect(screen.queryByLabelText("Сообщение ассистенту")).not.toBeInTheDocument();
    });

    it("shows a connection-lost message when the stream ends without done", async () => {
        const user = userEvent.setup();
        vi.mocked(streamMessage).mockResolvedValue({finished: false});

        renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Привет{Enter}");

        expect(
            await screen.findByText("Соединение прервано, попробуйте ещё раз"),
        ).toBeInTheDocument();
        await waitFor(() =>
            expect(screen.getByLabelText("Сообщение ассистенту")).not.toBeDisabled(),
        );
    });

    it("prefills the input from the ?q query param (landing hand-off)", async () => {
        render(
            <MemoryRouter initialEntries={["/chat?q=Моисей из Невеля"]}>
                <ChatPage />
            </MemoryRouter>,
        );

        const input = await screen.findByLabelText("Сообщение ассистенту");
        expect(input).toHaveValue("Моисей из Невеля");
    });

    it("shows «бесплатные сессии закончились» with a tariff CTA on free_sessions_limit", async () => {
        const user = userEvent.setup();
        vi.mocked(createSession).mockRejectedValue({
            response: {data: {detail: {code: "free_sessions_limit", message: "no more"}}},
        });
        vi.mocked(listSessions).mockResolvedValue([]);

        renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Привет{Enter}");

        expect(
            await screen.findByText(
                "Бесплатные сессии на сегодня закончились. Продолжите завтра или оформите тариф.",
            ),
        ).toBeInTheDocument();

        await user.click(screen.getByRole("button", {name: "Оформить тариф"}));
        expect(await screen.findByRole("dialog", {name: "Тарифы"})).toBeInTheDocument();
    });

    it("shows «лимит исчерпан» with a tariff CTA on daily_budget from the stream", async () => {
        const user = userEvent.setup();
        vi.mocked(streamMessage).mockRejectedValue(new ChatApiError("daily_budget", "limit"));

        renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Привет{Enter}");

        expect(
            await screen.findByText("Бесплатный лимит на сегодня исчерпан."),
        ).toBeInTheDocument();
        expect(screen.getByRole("button", {name: "Оформить тариф"})).toBeInTheDocument();
    });

    it("shows «слишком много запросов» without a tariff CTA on rate_limited", async () => {
        const user = userEvent.setup();
        vi.mocked(streamMessage).mockRejectedValue(new ChatApiError("rate_limited", "slow down"));

        renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Привет{Enter}");

        expect(
            await screen.findByText("Слишком много запросов. Подождите немного и попробуйте ещё раз."),
        ).toBeInTheDocument();
        expect(screen.queryByRole("button", {name: "Оформить тариф"})).not.toBeInTheDocument();
    });

    it("falls back to the generic send error for an unknown backend code", async () => {
        const user = userEvent.setup();
        vi.mocked(streamMessage).mockRejectedValue(new ChatApiError("weird_code", "???"));

        renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Привет{Enter}");

        expect(
            await screen.findByText("Не удалось отправить сообщение. Попробуйте ещё раз."),
        ).toBeInTheDocument();
    });

    it("tolerates a legacy string detail on session creation", async () => {
        const user = userEvent.setup();
        vi.mocked(createSession).mockRejectedValue({
            response: {data: {detail: "старая строковая ошибка"}},
        });
        vi.mocked(listSessions).mockResolvedValue([]);

        renderChat();

        const input = await screen.findByLabelText("Сообщение ассистенту");
        await user.type(input, "Привет{Enter}");

        expect(
            await screen.findByText("Не удалось создать поиск. Попробуйте ещё раз."),
        ).toBeInTheDocument();
        expect(screen.queryByRole("button", {name: "Оформить тариф"})).not.toBeInTheDocument();
    });

    it("uploads a scan: chip goes from «Обработка» to «Готово»", async () => {
        const user = userEvent.setup();
        let resolveUpload: (result: ScanUploadResult) => void = () => {};
        vi.mocked(uploadScan).mockImplementation(
            () =>
                new Promise<ScanUploadResult>((resolve) => {
                    resolveUpload = resolve;
                }),
        );

        renderChat();
        await screen.findByText("Ивановы из Одессы");

        const file = new File(["scan"], "metrika.jpg", {type: "image/jpeg"});
        await user.upload(screen.getByLabelText("Файл скана"), file);

        expect(await screen.findByText("Обработка…")).toBeInTheDocument();
        expect(screen.getByText("metrika.jpg")).toBeInTheDocument();

        resolveUpload(scanDone);
        expect(await screen.findByText("Готово")).toBeInTheDocument();
        expect(uploadScan).toHaveBeenCalledWith("s1", file);
    });

    it("opens the tariffs modal when the scan pool is exhausted (402)", async () => {
        const user = userEvent.setup();
        vi.mocked(uploadScan).mockRejectedValue(
            new ScanUploadError("no_scans_left", "Сканы закончились"),
        );

        renderChat();
        await screen.findByText("Ивановы из Одессы");

        await user.upload(
            screen.getByLabelText("Файл скана"),
            new File(["scan"], "metrika.jpg", {type: "image/jpeg"}),
        );

        await user.click(await screen.findByRole("button", {name: /Сканы закончились/}));
        expect(await screen.findByRole("dialog", {name: "Тарифы"})).toBeInTheDocument();
    });

    it("sends the message with scan_ids and moves the chip into the user bubble", async () => {
        const user = userEvent.setup();
        vi.mocked(uploadScan).mockResolvedValue(scanDone);

        renderChat();
        await screen.findByText("Ивановы из Одессы");

        await user.upload(
            screen.getByLabelText("Файл скана"),
            new File(["scan"], "metrika.jpg", {type: "image/jpeg"}),
        );
        await screen.findByText("Готово");

        await user.type(screen.getByLabelText("Сообщение ассистенту"), "Что в этом документе?{Enter}");

        await waitFor(() =>
            expect(streamMessage).toHaveBeenCalledWith(
                "s1",
                "Что в этом документе?",
                expect.anything(),
                expect.anything(),
                [7],
            ),
        );

        // chip left the input area (no more status/remove controls)…
        await waitFor(() => expect(screen.queryByText("Готово")).not.toBeInTheDocument());
        expect(
            screen.queryByRole("button", {name: "Удалить скан metrika.jpg"}),
        ).not.toBeInTheDocument();
        // …and lives on in the user bubble as thumbnail + file name
        expect(screen.getByText("metrika.jpg")).toBeInTheDocument();
        // extracted text is never rendered in the dialog
        expect(screen.queryByText(/Родился Иван/)).not.toBeInTheDocument();
    });

    it("refreshes the scans counter after an upload", async () => {
        const user = userEvent.setup();
        vi.mocked(getCredits)
            .mockResolvedValueOnce({searches_left: 3, scans_left: 5})
            .mockResolvedValue({searches_left: 3, scans_left: 4});
        vi.mocked(uploadScan).mockResolvedValue(scanDone);

        renderChat();
        expect(await screen.findByText(/Сканов: 5/)).toBeInTheDocument();

        await user.upload(
            screen.getByLabelText("Файл скана"),
            new File(["scan"], "metrika.jpg", {type: "image/jpeg"}),
        );

        expect(await screen.findByText(/Сканов: 4/)).toBeInTheDocument();
    });

    it("shows an inline error on the chip when the server rejects the file", async () => {
        const user = userEvent.setup();
        vi.mocked(uploadScan).mockRejectedValue(
            new ScanUploadError("too_large", "Файл больше 10 МБ — сожмите или обрежьте скан"),
        );

        renderChat();
        await screen.findByText("Ивановы из Одессы");

        await user.upload(
            screen.getByLabelText("Файл скана"),
            new File(["scan"], "metrika.jpg", {type: "image/jpeg"}),
        );

        expect(await screen.findByText(/сожмите или обрежьте скан/)).toBeInTheDocument();
    });

    it("201 with status:error in the body turns the chip into an error, not eternal processing", async () => {
        const user = userEvent.setup();
        vi.mocked(uploadScan).mockResolvedValue({
            ...scanDone,
            status: "error",
            extracted_text: "",
        });

        renderChat();
        await screen.findByText("Ивановы из Одессы");

        await user.upload(
            screen.getByLabelText("Файл скана"),
            new File(["scan"], "metrika.jpg", {type: "image/jpeg"}),
        );

        expect(await screen.findByText("Не удалось прочитать документ")).toBeInTheDocument();
        expect(screen.queryByText("Обработка…")).not.toBeInTheDocument();
        expect(screen.queryByText("Готово")).not.toBeInTheDocument();
        // the chip stays removable
        expect(screen.getByRole("button", {name: "Удалить скан metrika.jpg"})).toBeInTheDocument();
    });

    it("shows the «неуверенное чтение» badge on a done chip with low confidence", async () => {
        const user = userEvent.setup();
        vi.mocked(uploadScan).mockResolvedValue({
            ...scanDone,
            metadata: {...scanDone.metadata, confidence: "low"},
        });

        renderChat();
        await screen.findByText("Ивановы из Одессы");

        await user.upload(
            screen.getByLabelText("Файл скана"),
            new File(["scan"], "metrika.jpg", {type: "image/jpeg"}),
        );

        expect(await screen.findByText("Готово")).toBeInTheDocument();
        expect(screen.getByText("неуверенное чтение")).toBeInTheDocument();
    });
});
