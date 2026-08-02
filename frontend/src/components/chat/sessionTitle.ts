import type {ChatSessionSummary} from "@/api/chat";

const PREVIEW_LENGTH = 80;

/**
 * Coerce anything the backend might send into displayable text.
 * Never throws: strings pass through, objects yield their `content`,
 * everything else (numbers, booleans, null) is treated as garbage → "".
 */
function normalizeText(value: unknown): string {
    if (value == null) return "";
    if (typeof value === "string") return value.trim();
    if (typeof value === "object") {
        const content = (value as { content?: unknown }).content;
        return typeof content === "string" ? content.trim() : "";
    }
    return "";
}

export function sessionDisplayTitle(session: ChatSessionSummary): string {
    const title = normalizeText(session.title);
    if (title) return title;
    const preview = normalizeText(session.last_message);
    if (preview) {
        return preview.length > PREVIEW_LENGTH
            ? `${preview.slice(0, PREVIEW_LENGTH)}…`
            : preview;
    }
    return "Новый поиск";
}
