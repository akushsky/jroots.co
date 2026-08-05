import {describe, expect, it} from "vitest";
import {render, screen, within} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import AppChooser from "../AppChooser";

function renderChooser() {
    return render(
        <MemoryRouter>
            <AppChooser />
        </MemoryRouter>,
    );
}

describe("AppChooser", () => {
    it("renders both tool cards with correct destinations", () => {
        renderChooser();

        expect(screen.getByRole("heading", {name: "С чего начнём?"})).toBeInTheDocument();

        const chat = screen.getByTestId("tool-chat");
        expect(chat).toHaveAttribute("href", "/chat");
        expect(within(chat).getByText("Чат-ассистент")).toBeInTheDocument();

        const search = screen.getByTestId("tool-search");
        expect(search).toHaveAttribute("href", "/");
        expect(within(search).getByText("Профессиональный поиск")).toBeInTheDocument();
        expect(within(search).getByText(/Внезапные евреи/)).toBeInTheDocument();
    });
});
