import {beforeEach, describe, expect, it, vi} from "vitest";
import {render, screen} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import SearchPage from "../SearchPage";

vi.mock("@/api/api", () => ({
    fetchSources: vi.fn().mockResolvedValue([]),
    searchObjects: vi.fn(),
    fetchImage: vi.fn(),
    requestAccess: vi.fn(),
    clearImageCache: vi.fn(),
}));

describe("SearchPage cross-links", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("offers the AI assistant link leading to /chat", async () => {
        render(
            <MemoryRouter>
                <SearchPage />
            </MemoryRouter>,
        );

        const link = await screen.findByRole("link", {name: /Спросите ассистента/});
        expect(link).toHaveAttribute("href", "/chat");
        expect(link).toHaveTextContent("Не нашли сами? Спросите ассистента →");
    });
});
