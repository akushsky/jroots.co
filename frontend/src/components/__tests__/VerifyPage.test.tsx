import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {act, render, screen} from "@testing-library/react";
import {MemoryRouter, Route, Routes} from "react-router-dom";
import VerifyPage from "../VerifyPage";

function renderVerify() {
    return render(
        <MemoryRouter initialEntries={["/verify?token=abc"]}>
            <Routes>
                <Route path="/verify" element={<VerifyPage />} />
                <Route path="/landing" element={<div>LANDING</div>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("VerifyPage", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(new Response("ok", {status: 200})),
        );
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    it("redirects to /landing after the success countdown", async () => {
        renderVerify();

        // let the verify fetch resolve
        await act(async () => {});
        expect(screen.getByText(/Email успешно подтвержден/)).toBeInTheDocument();

        // run the 5-second countdown
        await act(async () => {
            vi.advanceTimersByTime(6000);
        });

        expect(screen.getByText("LANDING")).toBeInTheDocument();
    });
});
