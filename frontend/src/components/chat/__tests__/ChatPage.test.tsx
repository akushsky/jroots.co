import {beforeEach, describe, expect, it, vi} from "vitest";
import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter} from "react-router-dom";
import ChatPage from "../ChatPage";
import {createSession, getCredits, getSession, listSessions, streamMessage} from "@/api/chat";
import type {StreamCallbacks} from "@/api/chat";

vi.mock("@/api/chat", () => ({
    createSession: vi.fn(),
    listSessions: vi.fn(),
    getSession: vi.fn(),
    getCredits: vi.fn(),
    streamMessage: vi.fn(),
}));

const sessionSummary = {
    id: "s1",
    title: "Ивановы из Одессы",
    created_at: "2026-08-01T10:00:00Z",
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

        finish?.();
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
            expect(button).toBeDisabled();
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
});
