import {describe, expect, it, vi} from "vitest";
import {render, screen} from "@testing-library/react";
import {SessionSidebar} from "../SessionSidebar";
import {sessionDisplayTitle} from "../sessionTitle";
import type {ChatSessionSummary} from "@/api/chat";

const base: ChatSessionSummary = {id: "s1", created_at: "2026-08-01T10:00:00Z"};

describe("sessionDisplayTitle", () => {
    it("prefers a non-empty title", () => {
        expect(sessionDisplayTitle({...base, title: "Ивановы", last_message: "черновик"})).toBe("Ивановы");
    });

    it("falls back to last_message when title is missing or blank", () => {
        expect(sessionDisplayTitle({...base, last_message: "Ищу Штернов из Кишинёва"})).toBe(
            "Ищу Штернов из Кишинёва",
        );
        expect(sessionDisplayTitle({...base, title: "   ", last_message: "превью"})).toBe("превью");
    });

    it("truncates a long last_message to 80 chars with an ellipsis", () => {
        const long = "а".repeat(100);
        const result = sessionDisplayTitle({...base, last_message: long});
        expect(result).toBe(`${"а".repeat(80)}…`);
    });

    it("falls back to «Новый поиск» when both are empty", () => {
        expect(sessionDisplayTitle(base)).toBe("Новый поиск");
        expect(sessionDisplayTitle({...base, title: "", last_message: null})).toBe("Новый поиск");
    });

    it("survives a last_message sent as an object (backend type drift)", () => {
        const asObject = {content: "Рабиновичи из Бердичева"};
        expect(
            sessionDisplayTitle({...base, last_message: asObject as unknown as string}),
        ).toBe("Рабиновичи из Бердичева");
        // object without a string content — no crash, plain fallback
        expect(
            sessionDisplayTitle({...base, last_message: {id: 7} as unknown as string}),
        ).toBe("Новый поиск");
    });

    it("survives non-string scalars without throwing", () => {
        // non-string garbage is ignored, not stringified into a silly title
        expect(sessionDisplayTitle({...base, last_message: 42 as unknown as string})).toBe(
            "Новый поиск",
        );
        expect(
            sessionDisplayTitle({...base, last_message: undefined, title: undefined}),
        ).toBe("Новый поиск");
        expect(
            sessionDisplayTitle({...base, title: 0 as unknown as string, last_message: null}),
        ).toBe("Новый поиск");
    });
});

describe("SessionSidebar", () => {
    it("renders title, last_message fallback and «Новый поиск» per session", () => {
        render(
            <SessionSidebar
                sessions={[
                    {...base, id: "s1", title: "Ивановы из Одессы"},
                    {...base, id: "s2", last_message: "Штерны из Кишинёва"},
                    {...base, id: "s3"},
                ]}
                activeId={null}
                onSelect={vi.fn()}
                onNew={vi.fn()}
            />,
        );

        expect(screen.getByText("Ивановы из Одессы")).toBeInTheDocument();
        expect(screen.getByText("Штерны из Кишинёва")).toBeInTheDocument();
        // one «Новый поиск» is the header button, the second is the untitled session
        expect(screen.getAllByText("Новый поиск")).toHaveLength(2);
        expect(screen.queryByText("Поиск без названия")).not.toBeInTheDocument();
    });

    it("renders without crashing when last_message arrives as an object", () => {
        render(
            <SessionSidebar
                sessions={[
                    {...base, id: "s9", last_message: {content: "Объектное превью"} as unknown as string},
                ]}
                activeId={null}
                onSelect={vi.fn()}
                onNew={vi.fn()}
            />,
        );

        expect(screen.getByText("Объектное превью")).toBeInTheDocument();
    });
});
