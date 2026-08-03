import {afterAll, beforeEach, describe, expect, it, vi} from "vitest";
import {render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {Paywall} from "../Paywall";
import {createCheckout} from "@/api/payments";

vi.mock("@/api/payments", () => ({
    createCheckout: vi.fn(),
}));

const createCheckoutMock = vi.mocked(createCheckout);

const originalLocation = window.location;
const assignMock = vi.fn();

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

function tariffCard(testId: string) {
    return within(screen.getByTestId(testId));
}

describe("Paywall", () => {
    it("renders both tariffs and the pay-per-result row", () => {
        render(<Paywall />);

        expect(screen.getByTestId("tariff-delo")).toBeInTheDocument();
        expect(screen.getByTestId("tariff-researcher")).toBeInTheDocument();
        expect(screen.getByTestId("tariff-ppr")).toBeInTheDocument();
        expect(screen.getByText("Пакет «Дело»")).toBeInTheDocument();
        expect(screen.getByText("Подписка «Исследователь»")).toBeInTheDocument();
    });

    it("checkout on «Дело» posts the tariff and redirects to checkout_url", async () => {
        const user = userEvent.setup();
        createCheckoutMock.mockResolvedValue({checkout_url: "https://pay.example/delo"});
        render(<Paywall />);

        await user.click(tariffCard("tariff-delo").getByRole("button", {name: "Оформить"}));

        expect(createCheckoutMock).toHaveBeenCalledWith("delo", "polar");
        await waitFor(() => expect(assignMock).toHaveBeenCalledWith("https://pay.example/delo"));
    });

    it("shows a loading state on the clicked button while checkout is created", async () => {
        const user = userEvent.setup();
        let resolveCheckout!: (value: { checkout_url: string }) => void;
        createCheckoutMock.mockReturnValue(
            new Promise((resolve) => {
                resolveCheckout = resolve;
            }),
        );
        render(<Paywall />);

        const button = tariffCard("tariff-delo").getByRole("button", {name: "Оформить"});
        await user.click(button);

        expect(screen.getByText("Переход к оплате…")).toBeInTheDocument();
        expect(button).toBeDisabled();
        expect(assignMock).not.toHaveBeenCalled();

        resolveCheckout({checkout_url: "https://pay.example/delo"});
        await waitFor(() => expect(assignMock).toHaveBeenCalledWith("https://pay.example/delo"));
    });

    it("shows an inline error and does not redirect when checkout fails", async () => {
        const user = userEvent.setup();
        createCheckoutMock.mockRejectedValue(new Error("network down"));
        render(<Paywall />);

        await user.click(tariffCard("tariff-delo").getByRole("button", {name: "Оформить"}));

        expect(
            await tariffCard("tariff-delo").findByRole("alert"),
        ).toHaveTextContent("Не удалось открыть страницу оплаты. Попробуйте ещё раз.");
        expect(assignMock).not.toHaveBeenCalled();
    });

    it("shows the backend detail message when the API rejects the checkout", async () => {
        const user = userEvent.setup();
        createCheckoutMock.mockRejectedValue({
            isAxiosError: true,
            response: {data: {detail: "Payment provider unavailable"}},
        });
        render(<Paywall />);

        await user.click(tariffCard("tariff-delo").getByRole("button", {name: "Оформить"}));

        expect(await tariffCard("tariff-delo").findByRole("alert")).toHaveTextContent(
            "Payment provider unavailable",
        );
    });

    it("switches provider to «Крипта» and sends nowpayments", async () => {
        const user = userEvent.setup();
        createCheckoutMock.mockResolvedValue({checkout_url: "https://pay.example/crypto"});
        render(<Paywall />);

        const card = tariffCard("tariff-delo");
        await user.click(card.getByRole("radio", {name: "Крипта"}));
        await user.click(card.getByRole("button", {name: "Оформить"}));

        expect(createCheckoutMock).toHaveBeenCalledWith("delo", "nowpayments");
        await waitFor(() => expect(assignMock).toHaveBeenCalledWith("https://pay.example/crypto"));
    });

    it("locks the subscription tariff to «Карта»: other providers are disabled", async () => {
        const user = userEvent.setup();
        createCheckoutMock.mockResolvedValue({checkout_url: "https://pay.example/sub"});
        render(<Paywall />);

        const card = tariffCard("tariff-researcher");
        expect(card.getByRole("radio", {name: "Карта"})).toBeEnabled();
        expect(card.getByRole("radio", {name: "Крипта"})).toBeDisabled();
        expect(card.getByRole("radio", {name: "₽"})).toBeDisabled();

        await user.click(card.getByRole("button", {name: "Оформить"}));
        expect(createCheckoutMock).toHaveBeenCalledWith("researcher", "polar");
    });

    it("pay-per-result button checks out the ppr tariff", async () => {
        const user = userEvent.setup();
        createCheckoutMock.mockResolvedValue({checkout_url: "https://pay.example/ppr"});
        render(<Paywall />);

        await user.click(
            tariffCard("tariff-ppr").getByRole("button", {name: "Разблокировать одну запись — $3"}),
        );

        expect(createCheckoutMock).toHaveBeenCalledWith("ppr", "polar");
        await waitFor(() => expect(assignMock).toHaveBeenCalledWith("https://pay.example/ppr"));
    });
});
