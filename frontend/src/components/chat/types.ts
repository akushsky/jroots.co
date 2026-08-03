import type {CappedReason} from "@/api/chat";

export interface DisplayMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    /** Streaming has started but no tokens arrived yet — show "печатает…". */
    pending?: boolean;
    /** Intermediate agent reasoning ("Ход поиска"), accumulated from step events. */
    steps?: string;
    /** True while this message is the actively streaming one — steps accordion stays open. */
    live?: boolean;
    capped?: CappedReason | null;
    error?: boolean;
}
