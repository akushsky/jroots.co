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
                message={assistantMessage({steps: "Искал в метриках", live: false})}
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
                message={assistantMessage({steps: "Промежуточный шаг", live: true})}
            />,
        );

        expect(screen.getByText("Промежуточный шаг")).toBeInTheDocument();
    });

    it("expands on click to reveal the steps", async () => {
        const user = userEvent.setup();
        render(
            <ChatMessageBubble
                message={assistantMessage({steps: "Скрытый шаг", live: false})}
            />,
        );

        await user.click(screen.getByText("Ход поиска"));
        expect(await screen.findByText("Скрытый шаг")).toBeInTheDocument();
    });

    it("renders no accordion when there are no steps", () => {
        render(<ChatMessageBubble message={assistantMessage({})} />);
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
