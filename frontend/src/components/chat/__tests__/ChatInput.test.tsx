import {describe, expect, it, vi} from "vitest";
import {fireEvent, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {ChatInput} from "../ChatInput";
import type {ScanAttachment} from "../scans";
import {PaywallContext} from "../PaywallContext";

function baseProps(overrides: Partial<Parameters<typeof ChatInput>[0]> = {}) {
    return {
        disabled: false,
        attachments: [] as ScanAttachment[],
        onAttachFile: vi.fn(),
        onRemoveAttachment: vi.fn(),
        onSend: vi.fn(),
        ...overrides,
    };
}

function makeFile(name: string, type: string, size: number): File {
    const file = new File(["x"], name, {type});
    Object.defineProperty(file, "size", {value: size});
    return file;
}

const doneAttachment: ScanAttachment = {
    localId: "temp-1",
    fileName: "metrika.jpg",
    previewUrl: "blob:mock-1",
    status: "done",
    scanId: 7,
};

describe("ChatInput scan attachments", () => {
    it("rejects an oversized file with an inline error and does not attach it", async () => {
        const user = userEvent.setup();
        const props = baseProps();
        render(<ChatInput {...props} />);

        await user.upload(
            screen.getByLabelText("Файл скана"),
            makeFile("huge.jpg", "image/jpeg", 11 * 1024 * 1024),
        );

        expect(screen.getByText(/huge\.jpg: Файл больше 10 МБ/)).toBeInTheDocument();
        expect(props.onAttachFile).not.toHaveBeenCalled();
    });

    it("rejects an unsupported format with an inline error", async () => {
        // fireEvent.change: userEvent.upload honors the accept attribute and
        // would silently drop a .pdf before our own validation runs.
        const props = baseProps();
        render(<ChatInput {...props} />);

        fireEvent.change(screen.getByLabelText("Файл скана"), {
            target: {files: [makeFile("doc.pdf", "application/pdf", 100)]},
        });

        expect(await screen.findByText(/doc\.pdf: Поддерживаются только JPEG, PNG и TIFF/)).toBeInTheDocument();
        expect(props.onAttachFile).not.toHaveBeenCalled();
    });

    it("attaches a valid file and clears a previous validation error", async () => {
        const props = baseProps();
        render(<ChatInput {...props} />);

        const input = screen.getByLabelText("Файл скана");
        fireEvent.change(input, {target: {files: [makeFile("doc.pdf", "application/pdf", 100)]}});
        expect(await screen.findByText(/Поддерживаются только/)).toBeInTheDocument();

        const valid = makeFile("metrika.jpg", "image/jpeg", 100);
        fireEvent.change(input, {target: {files: [valid]}});
        expect(props.onAttachFile).toHaveBeenCalledWith(valid);
        expect(screen.queryByText(/Поддерживаются только/)).not.toBeInTheDocument();
    });

    it("blocks sending while any attachment is still uploading", async () => {
        const user = userEvent.setup();
        const props = baseProps({
            attachments: [{...doneAttachment, status: "uploading", scanId: undefined}],
        });
        render(<ChatInput {...props} />);

        expect(screen.getByText("Обработка…")).toBeInTheDocument();
        await user.type(screen.getByLabelText("Сообщение ассистенту"), "текст");
        expect(screen.getByRole("button", {name: "Отправить"})).toBeDisabled();

        await user.keyboard("{Enter}");
        expect(props.onSend).not.toHaveBeenCalled();
    });

    it("sends typed content once attachments are done", async () => {
        const user = userEvent.setup();
        const props = baseProps({attachments: [doneAttachment]});
        render(<ChatInput {...props} />);

        expect(screen.getByText("Готово")).toBeInTheDocument();
        await user.type(screen.getByLabelText("Сообщение ассистенту"), "Вот документ{Enter}");
        expect(props.onSend).toHaveBeenCalledWith("Вот документ");
    });

    it("removes an attachment via its delete button", async () => {
        const user = userEvent.setup();
        const props = baseProps({attachments: [doneAttachment]});
        render(<ChatInput {...props} />);

        await user.click(screen.getByRole("button", {name: "Удалить скан metrika.jpg"}));
        expect(props.onRemoveAttachment).toHaveBeenCalledWith("temp-1");
    });

    it("opens the paywall from the «Сканы закончились» chip", async () => {
        const user = userEvent.setup();
        const openPaywall = vi.fn();
        const props = baseProps({
            attachments: [{...doneAttachment, status: "error", errorCode: "no_scans_left"}],
        });
        render(
            <PaywallContext.Provider value={openPaywall}>
                <ChatInput {...props} />
            </PaywallContext.Provider>,
        );

        await user.click(screen.getByRole("button", {name: /Сканы закончились/}));
        expect(openPaywall).toHaveBeenCalled();
    });
});
