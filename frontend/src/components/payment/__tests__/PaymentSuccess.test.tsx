import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {act, render, screen} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import PaymentSuccess from "../PaymentSuccess";
import {getCredits} from "@/api/chat";

vi.mock("@/api/chat", () => ({
    getCredits: vi.fn(),
}));

const getCreditsMock = vi.mocked(getCredits);

async function advance(ms: number) {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
    });
}

describe("PaymentSuccess", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers();
        getCreditsMock.mockResolvedValue({searches_left: 25, scans_left: 10});
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    function renderPage() {
        return render(
            <MemoryRouter>
                <PaymentSuccess />
            </MemoryRouter>,
        );
    }

    it("shows the success message and the balance from getCredits", async () => {
        renderPage();
        await advance(0);

        expect(screen.getByText("Оплата прошла")).toBeInTheDocument();
        const balance = screen.getByText(
            (_, element) =>
                element?.tagName === "P" &&
                (element.textContent ?? "").includes("Осталось поисков: 25"),
        );
        expect(balance).toHaveTextContent("Осталось поисков: 25 · Сканов: 10");
        expect(screen.getByRole("link", {name: "В чат"})).toHaveAttribute("href", "/chat");
    });

    it("polls getCredits until the 15s timeout, then stops", async () => {
        renderPage();
        await advance(0);
        expect(getCreditsMock).toHaveBeenCalledTimes(1);
        expect(screen.getByText(/Обновляем баланс/)).toBeInTheDocument();

        await advance(2500);
        expect(getCreditsMock).toHaveBeenCalledTimes(2);

        await advance(15000);
        const callsAfterTimeout = getCreditsMock.mock.calls.length;
        expect(callsAfterTimeout).toBeGreaterThanOrEqual(6);
        expect(screen.queryByText(/Обновляем баланс/)).not.toBeInTheDocument();

        await advance(10000);
        expect(getCreditsMock.mock.calls.length).toBe(callsAfterTimeout);
    });

    it("keeps the page usable when the balance read fails", async () => {
        getCreditsMock.mockRejectedValue(new Error("unauthorized"));
        renderPage();
        await advance(0);

        expect(screen.getByText("Оплата прошла")).toBeInTheDocument();
        expect(screen.queryByText(/Осталось поисков/)).not.toBeInTheDocument();
        expect(screen.getByRole("link", {name: "В чат"})).toBeInTheDocument();
    });
});
