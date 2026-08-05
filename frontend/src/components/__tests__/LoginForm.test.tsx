import {beforeEach, describe, expect, it, vi} from "vitest";
import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter, Route, Routes} from "react-router-dom";
import LoginForm from "../LoginForm";
import {userLogin} from "@/api/api";

vi.mock("@/api/api", () => ({
    userLogin: vi.fn(),
    clearImageCache: vi.fn(),
}));

function renderLogin() {
    return render(
        <MemoryRouter initialEntries={["/login"]}>
            <Routes>
                <Route path="/login" element={<LoginForm />} />
                <Route path="/landing" element={<div>LANDING</div>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("LoginForm", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(userLogin).mockResolvedValue({access_token: "tok", token_type: "bearer"});
    });

    it("redirects to /landing after a successful login", async () => {
        const user = userEvent.setup();
        renderLogin();

        await user.type(screen.getByPlaceholderText("Email"), "u@test.com");
        await user.type(screen.getByPlaceholderText("Пароль"), "secret");
        await user.click(screen.getByRole("button", {name: "Войти"}));

        expect(await screen.findByText("LANDING")).toBeInTheDocument();
        await waitFor(() => expect(userLogin).toHaveBeenCalledWith("u@test.com", "secret"));
    });
});
