import ReactMarkdown, {type Components} from "react-markdown";
import {AlertTriangle} from "lucide-react";
import {cn} from "@/lib/utils";
import {Tooltip, TooltipContent, TooltipTrigger} from "@/components/ui/tooltip";
import type {DisplayMessage} from "./types";
import {StepsBlock} from "./StepsBlock";

const LOCK_TEASER = /доступно в полной версии/i;

function LockChip({label}: { label: string }) {
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-1 text-xs bg-muted text-muted-foreground rounded-full px-2 py-0.5 cursor-help align-baseline">
                    🔒 {label}
                </span>
            </TooltipTrigger>
            <TooltipContent>Доступно в пакете «Дело»</TooltipContent>
        </Tooltip>
    );
}

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
    em: ({children}) =>
        typeof children === "string" && LOCK_TEASER.test(children) ? (
            <LockChip label={children} />
        ) : (
            <em className="italic text-muted-foreground">{children}</em>
        ),
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
            <div className={cn("max-w-[85%] md:max-w-[75%] min-w-0 flex flex-col gap-1", isUser && "items-end")}>
                {!isUser && message.steps && (
                    <StepsBlock steps={message.steps} live={message.live} />
                )}
                <div
                    className={cn(
                        "rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-xs",
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
        </div>
    );
}
