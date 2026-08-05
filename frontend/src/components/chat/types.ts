import type {CappedReason} from "@/api/chat";

export interface MessageScan {
    fileName: string;
    /** Object URL of the uploaded file — thumbnail inside the user bubble. */
    previewUrl: string;
}

export interface DisplayMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    /** Streaming has started but no tokens arrived yet — show "печатает…". */
    pending?: boolean;
    /** Intermediate agent reasoning ("Ход поиска") — one entry per step event, rendered as a list. */
    steps?: string[];
    /** Agent's search journal from <searchlog> blocks — "Проверенные базы" subsection. */
    searchlog?: string[];
    /** True while this message is the actively streaming one — steps accordion stays open. */
    live?: boolean;
    /** Scans attached to a user message (thumbnail + file name only; extracted text stays in agent context). */
    scans?: MessageScan[];
    capped?: CappedReason | null;
    error?: boolean;
    /** Error message carries a tariff CTA (opens the paywall modal). */
    paywallAction?: boolean;
}
