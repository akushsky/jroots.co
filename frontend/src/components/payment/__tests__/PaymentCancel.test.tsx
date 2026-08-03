import {describe, expect, it} from "vitest";
import {render, screen} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import PaymentCancel from "../PaymentCancel";

describe("PaymentCancel", () => {
    it("renders the cancellation message with a link back to the chat", () => {
        render(
            <MemoryRouter>
                <PaymentCancel />
            </MemoryRouter>,
        );

        expect(screen.getByTestId("payment-cancel")).toBeInTheDocument();
        expect(screen.getByText("Оплата отменена")).toBeInTheDocument();
        expect(screen.getByRole("link", {name: "Назад в чат"})).toHaveAttribute("href", "/chat");
    });
});
