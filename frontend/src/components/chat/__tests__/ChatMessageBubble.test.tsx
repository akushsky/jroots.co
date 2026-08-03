import {describe, expect, it, vi} from "vitest";
import {fireEvent, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {ChatMessageBubble} from "../ChatMessageBubble";
import {PaywallContext} from "../PaywallContext";
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
    it("renders the «доступно в полной версии» emphasis as an explicit lock chip", () => {
        render(
            <ChatMessageBubble
                message={assistantMessage({
                    content: "Нашёл запись: 🔒 _доступно в полной версии_",
                })}
            />,
        );

        const chip = screen.getByRole("button", {name: /🔒 в полной версии/});
        expect(chip).toBeInTheDocument();
        expect(chip).toHaveClass("bg-muted");
    });

    it("opens the paywall when the lock chip is clicked", async () => {
        const user = userEvent.setup();
        const openPaywall = vi.fn();
        render(
            <PaywallContext.Provider value={openPaywall}>
                <ChatMessageBubble
                    message={assistantMessage({
                        content: "Нашёл запись: 🔒 _доступно в полной версии_",
                    })}
                />
            </PaywallContext.Provider>,
        );

        await user.click(screen.getByRole("button", {name: /в полной версии/}));
        expect(openPaywall).toHaveBeenCalledTimes(1);
    });

    it("renders the «🖼 🔒» image teaser as a clickable image chip", async () => {
        const user = userEvent.setup();
        const openPaywall = vi.fn();
        render(
            <PaywallContext.Provider value={openPaywall}>
                <ChatMessageBubble
                    message={assistantMessage({content: "Фото документа: 🖼 🔒"})}
                />
            </PaywallContext.Provider>,
        );

        const chip = screen.getByRole("button", {name: /🖼 🔒 в полной версии/});
        await user.click(chip);
        expect(openPaywall).toHaveBeenCalledTimes(1);
        // surrounding text is untouched
        expect(screen.getByText(/Фото документа:/)).toBeInTheDocument();
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

describe("ChatMessageBubble inline images", () => {
    it("renders markdown images as lazy thumbnails", () => {
        render(
            <ChatMessageBubble
                message={assistantMessage({
                    content: "Скан записи: ![ревизия 1816](https://example.com/scan.jpg)",
                })}
            />,
        );

        const img = screen.getByRole("img", {name: "ревизия 1816"});
        expect(img).toHaveAttribute("loading", "lazy");
        expect(img).toHaveAttribute("src", "https://example.com/scan.jpg");
        expect(img.className).toContain("max-h-[200px]");
    });

    it("opens a lightbox with the full image on click", async () => {
        const user = userEvent.setup();
        render(
            <ChatMessageBubble
                message={assistantMessage({
                    content: "![ревизия 1816](https://example.com/scan.jpg)",
                })}
            />,
        );

        await user.click(screen.getByRole("button", {name: /Открыть изображение/}));
        const dialog = screen.getByRole("dialog");
        expect(dialog).toBeInTheDocument();
        // thumbnail + lightbox copy
        expect(screen.getAllByRole("img", {name: "ревизия 1816"})).toHaveLength(2);
    });

    it("falls back to an «изображение недоступно» block when the image fails to load", () => {
        render(
            <ChatMessageBubble
                message={assistantMessage({
                    content: "![метрика Одессы](https://hotlink-blocked.example/x.png)",
                })}
            />,
        );

        fireEvent.error(screen.getByRole("img", {name: "метрика Одессы"}));
        expect(
            screen.getByText("Изображение недоступно: метрика Одессы"),
        ).toBeInTheDocument();
        expect(screen.queryByRole("img")).not.toBeInTheDocument();
    });
});
