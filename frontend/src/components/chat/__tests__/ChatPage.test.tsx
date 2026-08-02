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
