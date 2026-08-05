import {afterAll, beforeEach, describe, expect, it, vi} from "vitest";
import type {ComponentProps} from "react";
import {render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter, Route, Routes, useSearchParams} from "react-router-dom";
import LandingPage from "../LandingPage";
import {createCheckout} from "@/api/payments";
import {AuthContext} from "@/contexts/AuthContext";

vi.mock("@/api/payments", () => ({
    createCheckout: vi.fn(),
}));

const createCheckoutMock = vi.mocked(createCheckout);

const originalLocation = window.location;
const assignMock = vi.fn();

type AuthValue = ComponentProps<typeof AuthContext.Provider>["value"];

const GUEST_AUTH: AuthValue = {user: null, login: () => {}, logout: () => {}, isAuthenticated: false};
const LOGGED_IN_AUTH: AuthValue = {
    user: {email: "u@test.com", username: "user", is_verified: true},
    login: () => {},
    logout: () => {},
    isAuthenticated: true,
};

beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "location", {
        configurable: true,
        value: {...originalLocation, assign: assignMock},
    });
});

afterAll(() => {
    Object.defineProperty(window, "location", {configurable: true, value: originalLocation});
});

function ChatStub() {
    const [params] = useSearchParams();
    return <div>CHAT q={params.get("q")}</div>;
}

function renderLanding(auth: AuthValue = GUEST_AUTH) {
    return render(
        <MemoryRouter initialEntries={["/landing"]}>
            <AuthContext.Provider value={auth}>
                <Routes>
                    <Route path="/landing" element={<LandingPage />} />
                    <Route path="/chat" element={<ChatStub />} />
                </Routes>
            </AuthContext.Provider>
        </MemoryRouter>,
    );
}

describe("LandingPage", () => {
    it("renders hero, steps, examples, tariffs and article stubs", () => {
        renderLanding();

        expect(
            screen.getByRole("heading", {name: "Найдите документы вашей семьи для репатриации"}),
        ).toBeInTheDocument();
        expect(screen.getByLabelText("Кого ищете")).toBeInTheDocument();

        expect(screen.getByRole("heading", {name: "Как это работает"})).toBeInTheDocument();
        expect(screen.getByText("Расскажите, кого ищете")).toBeInTheDocument();
        expect(screen.getByText("Ассистент ищет по архивам")).toBeInTheDocument();
        expect(screen.getByText("Получите документы")).toBeInTheDocument();

        expect(screen.getByRole("heading", {name: "Так выглядит поиск"})).toBeInTheDocument();
        expect(screen.getByText(/Роза Гольдберг/)).toBeInTheDocument();
        expect(screen.getByText(/Абрам Лейбович/)).toBeInTheDocument();

        expect(screen.getByText("Пакет «Дело»")).toBeInTheDocument();
        expect(screen.getByText("Подписка «Исследователь»")).toBeInTheDocument();

        expect(screen.getByText("Как доказать еврейские корни")).toBeInTheDocument();
        expect(screen.getByText("Документы для репатриации из архивов")).toBeInTheDocument();
        expect(screen.getByText("Метрические книги: что это и где искать")).toBeInTheDocument();
    });

    it("leads from the hero input to /chat with the ?q prefilled", async () => {
        const user = userEvent.setup();
        renderLanding();

        await user.type(screen.getByLabelText("Кого ищете"), "Ивановы из Одессы");
        await user.click(screen.getByRole("button", {name: /Начать поиск/}));

        expect(await screen.findByText("CHAT q=Ивановы из Одессы")).toBeInTheDocument();
    });

    it("does not navigate on an empty hero query", async () => {
        const user = userEvent.setup();
        renderLanding();

        await user.type(screen.getByLabelText("Кого ищете"), "   ");
        expect(screen.getByRole("button", {name: /Начать поиск/})).toBeDisabled();
        expect(screen.queryByText(/CHAT q=/)).not.toBeInTheDocument();
    });

    it("tariff CTA opens the checkout flow", async () => {
        const user = userEvent.setup();
        createCheckoutMock.mockResolvedValue({checkout_url: "https://pay.example/delo"});
        renderLanding();

        const card = screen.getByTestId("tariff-delo");
        await user.click(within(card).getByRole("button", {name: "Оформить"}));

        expect(createCheckoutMock).toHaveBeenCalledWith("delo", "polar");
        await waitFor(() => expect(assignMock).toHaveBeenCalledWith("https://pay.example/delo"));
    });

    it("renders the two-tools section with the pro search card", () => {
        renderLanding();

        expect(screen.getByRole("heading", {name: "Два инструмента"})).toBeInTheDocument();
        expect(screen.getByRole("heading", {name: "AI-ассистент"})).toBeInTheDocument();
        expect(
            screen.getByRole("heading", {name: "Профессиональный поиск по архивам"}),
        ).toBeInTheDocument();
        expect(screen.getByText("Проект «Внезапные евреи»")).toBeInTheDocument();
        // pro search is always public — straight to SearchPage
        expect(screen.getByTestId("tool-search-cta")).toHaveAttribute("href", "/");
    });

    it("points guest CTAs at /signup", () => {
        renderLanding(GUEST_AUTH);

        expect(screen.getByTestId("header-auth-cta")).toHaveTextContent("Создать аккаунт");
        expect(screen.getByTestId("header-auth-cta")).toHaveAttribute("href", "/signup");
        expect(screen.getByTestId("hero-auth-cta")).toHaveAttribute("href", "/signup");
        expect(screen.getByTestId("tool-chat-cta")).toHaveAttribute("href", "/signup");
    });

    it("points logged-in CTAs at the /app chooser", () => {
        renderLanding(LOGGED_IN_AUTH);

        expect(screen.getByTestId("header-auth-cta")).toHaveTextContent("Перейти в чат");
        expect(screen.getByTestId("header-auth-cta")).toHaveAttribute("href", "/app");
        expect(screen.getByTestId("hero-auth-cta")).toHaveAttribute("href", "/app");
        expect(screen.getByTestId("tool-chat-cta")).toHaveAttribute("href", "/app");
    });
});
