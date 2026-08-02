import ReactMarkdown, {type Components} from "react-markdown";
import {AlertTriangle} from "lucide-react";
import {cn} from "@/lib/utils";
import type {DisplayMessage} from "./types";

const markdownComponents: Components = {
    p: ({children}) => <p className="mb-2 last:mb-0">{children}</p>,
    ul: ({children}) => <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>,
    ol: ({children}) => <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>,
    h3: ({children}) => <h3 className="font-display text-lg font-semibold mt-3 mb-1">{children}</h3>,
    a: ({href, children}) => (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline">
            {children}
        </a>
    ),
    strong: ({children}) => <strong className="font-semibold">{children}</strong>,
    code: ({children}) => (
        <code className="bg-muted px-1 py-0.5 rounded text-[0.85em]">{children}</code>
    ),
};

function TypingIndicator() {
    return (
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <span>печатает</span>
            <span className="inline-flex gap-0.5">
                {[0, 1, 2].map((i) => (
                    <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-muted-foreground/70 animate-bounce"
                        style={{animationDelay: `${i * 150}ms`}}
                    />
                ))}
            </span>
        </span>
    );
}

export function ChatMessageBubble({message}: { message: DisplayMessage }) {
    const isUser = message.role === "user";

    return (
        <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
            <div
                className={cn(
                    "max-w-[85%] md:max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-xs",
                    isUser
                        ? "bg-accent text-accent-foreground rounded-br-md whitespace-pre-wrap"
                        : "bg-secondary text-secondary-foreground rounded-bl-md",
                    message.error && "bg-destructive/10 text-destructive border border-destructive/30",
                )}
            >
                {message.pending ? (
                    <TypingIndicator />
                ) : isUser ? (
                    message.content
                ) : (
                    <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
                )}
                {message.capped && !message.error && (
                    <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground bg-background/60 border border-border rounded-full px-2.5 py-1">
                        <AlertTriangle className="w-3 h-3" />
                        Ответ сокращён — лимит сложной задачи
                    </div>
                )}
            </div>
        </div>
    );
}
