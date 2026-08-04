import {beforeEach, describe, expect, it, vi} from "vitest";
import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter} from "react-router-dom";
import RegisterForm from "../RegisterForm";
import {userRegister} from "@/api/api";

vi.mock("@/api/api", () => ({
    userRegister: vi.fn(),
    clearImageCache: vi.fn(),
}));

vi.mock("@fingerprintjs/fingerprintjs", () => ({
    default: {
        load: vi.fn(async () => ({
            get: async () => ({visitorId: "fp-visitor-123"}),
        })),
    },
}));

vi.mock("@hcaptcha/react-hcaptcha", () => ({
    default: ({onVerify}: { onVerify: (token: string) => void }) => (
        <button type="button" data-testid="captcha" onClick={() => onVerify("captcha-token")}>
            captcha
        </button>
    ),
}));

function renderForm() {
    return render(
        <MemoryRouter>
            <RegisterForm />
        </MemoryRouter>,
    );
}

describe("RegisterForm fingerprint", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(userRegister).mockResolvedValue({message: "ok"});
    });

    it("sends the fingerprintjs visitorId in the register request", async () => {
        const user = userEvent.setup();
        renderForm();

        await user.type(screen.getByPlaceholderText("Логин"), "testuser");
        await user.type(screen.getByPlaceholderText("Email"), "t@example.com");
        await user.type(screen.getByPlaceholderText("Пароль"), "secret123");
        await user.click(screen.getByTestId("captcha"));
        await user.click(screen.getByRole("button", {name: "Зарегистрироваться"}));

        await waitFor(() =>
            expect(userRegister).toHaveBeenCalledWith(
                "testuser",
                "t@example.com",
                "secret123",
                "",
                "captcha-token",
                "fp-visitor-123",
            ),
        );
    });
});
