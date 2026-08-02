import type {CappedReason} from "@/api/chat";

export interface DisplayMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    /** Streaming has started but no tokens arrived yet — show "печатает…". */
    pending?: boolean;
    capped?: CappedReason | null;
    error?: boolean;
}
