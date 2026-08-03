import {describe, expect, it} from "vitest";
import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {ChatMessageBubble} from "../ChatMessageBubble";
import type {DisplayMessage} from "../types";

function assistantMessage(patch: Partial<DisplayMessage>): DisplayMessage {
    return {id: "m1", role: "assistant", content: "Ответ ассистента", ...patch};
}

describe("ChatMessageBubble steps accordion", () => {
    it("renders «Ход поиска» collapsed by default after the stream finished", () => {
        render(
            <ChatMessageBubble
                message={assistantMessage({steps: ["Искал в метриках"], live: false})}
            />,
        );

        expect(screen.getByText("Ход поиска")).toBeInTheDocument();
        // collapsed: step content is not rendered
        expect(screen.queryByText("Искал в метриках")).not.toBeInTheDocument();
        // the answer itself is always visible
        expect(screen.getByText("Ответ ассистента")).toBeInTheDocument();
    });

    it("stays open and live while streaming", () => {
        render(
            <ChatMessageBubble
                message={assistantMessage({steps: ["Промежуточный шаг"], live: true})}
            />,
        );

        expect(screen.getByText("Промежуточный шаг")).toBeInTheDocument();
    });

    it("expands on click to reveal the steps", async () => {
        const user = userEvent.setup();
        render(
            <ChatMessageBubble
                message={assistantMessage({steps: ["Скрытый шаг"], live: false})}
            />,
        );

        await user.click(screen.getByText("Ход поиска"));
        expect(await screen.findByText("Скрытый шаг")).toBeInTheDocument();
    });

    it("renders each step as a separate list item, never glued together", () => {
        const {container} = render(
            <ChatMessageBubble
                message={assistantMessage({
                    steps: ["…для Самары (Куйбышеве", "Спасибо! У меня есть базы", "База pomnim.online"],
                    live: true,
                })}
            />,
        );

        const items = container.querySelectorAll('[data-testid="steps-block"] li');
        expect(items).toHaveLength(3);
        // texts live in separate nodes — no «КуйбышевеСпасибо» glue
        expect(items[0]).toHaveTextContent("1.…для Самары (Куйбышеве");
        expect(items[1]).toHaveTextContent("2.Спасибо! У меня есть базы");
        expect(items[2]).toHaveTextContent("3.База pomnim.online");
    });

    it("renders no accordion when there are no steps", () => {
        render(<ChatMessageBubble message={assistantMessage({})} />);
        expect(screen.queryByText("Ход поиска")).not.toBeInTheDocument();
    });

    it("renders no accordion when steps are all blank", () => {
        render(<ChatMessageBubble message={assistantMessage({steps: ["  ", ""]})} />);
        expect(screen.queryByText("Ход поиска")).not.toBeInTheDocument();
    });
});

describe("ChatMessageBubble lock teaser", () => {
    it("renders the «доступно в полной версии» emphasis as a lock chip", () => {
        render(
            <ChatMessageBubble
                message={assistantMessage({
                    content: "Нашёл запись: 🔒 _доступно в полной версии_",
                })}
            />,
        );

        const chip = screen.getByText(/доступно в полной версии/);
        expect(chip).toBeInTheDocument();
        expect(chip.closest("span")).toHaveClass("bg-muted");
    });

    it("keeps unrelated emphasis as plain italic text", () => {
        render(
            <ChatMessageBubble
                message={assistantMessage({content: "Это _важно_ отметить"})}
            />,
        );

        const em = screen.getByText("важно");
        expect(em.tagName.toLowerCase()).toBe("em");
    });
});
