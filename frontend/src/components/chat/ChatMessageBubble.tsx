import {Children, useState, type ReactNode} from "react";
import ReactMarkdown, {type Components} from "react-markdown";
import remarkGfm from "remark-gfm";
import {AlertTriangle} from "lucide-react";
import {cn} from "@/lib/utils";
import {Tooltip, TooltipContent, TooltipTrigger} from "@/components/ui/tooltip";
import type {DisplayMessage} from "./types";
import {StepsBlock} from "./StepsBlock";
import {useOpenPaywall} from "./PaywallContext";

const LOCK_TEASER = /доступно в полной версии/i;
const IMAGE_LOCK_PRESENT = /🖼\s*🔒/;
const IMAGE_LOCK_EXACT = /^🖼\s*🔒$/;
const IMAGE_LOCK_SEGMENT = /(🖼\s*🔒)/g;
const LOCK_TOOLTIP = "Полная запись со ссылкой на источник — пакет «Дело» $25";

function LockChip({image = false}: { image?: boolean }) {
    const openPaywall = useOpenPaywall();
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <button
                    type="button"
                    onClick={openPaywall}
                    className="inline-flex items-center gap-1 text-xs bg-muted hover:bg-accent/20 border border-border rounded-full px-2 py-0.5 cursor-pointer align-baseline transition-colors"
                >
                    {image ? "🖼 🔒 в полной версии" : "🔒 в полной версии"}
                </button>
            </TooltipTrigger>
            <TooltipContent>{LOCK_TOOLTIP}</TooltipContent>
        </Tooltip>
    );
}

/** Replace backend's teaser placeholder «🖼 🔒» in plain text with a clickable chip. */
function withImageLockChips(children: ReactNode): ReactNode {
    return Children.map(children, (child) => {
        if (typeof child !== "string" || !IMAGE_LOCK_PRESENT.test(child)) return child;
        return child
            .split(IMAGE_LOCK_SEGMENT)
            .map((part, index) =>
                IMAGE_LOCK_EXACT.test(part) ? <LockChip key={index} image /> : part,
            );
    });
}

function MarkdownImage({src, alt}: { src?: string; alt?: string }) {
    const [failed, setFailed] = useState(false);
    const [open, setOpen] = useState(false);

    if (!src || failed) {
        return (
            <span className="block my-2 rounded-md border border-dashed border-border bg-muted/50 px-3 py-4 text-xs text-muted-foreground text-center">
                Изображение недоступно{alt ? `: ${alt}` : ""}
            </span>
        );
    }

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                className="block my-2 cursor-zoom-in"
                aria-label={alt ? `Открыть изображение: ${alt}` : "Открыть изображение"}
            >
                <img
                    src={src}
                    alt={alt ?? ""}
                    loading="lazy"
                    onError={() => setFailed(true)}
                    className="max-h-[200px] rounded-lg border border-border object-cover shadow-xs"
                />
            </button>
            {open && (
                // span, not div: the markdown <p> renderer may be an ancestor
                <span
                    role="dialog"
                    aria-label={alt || "Просмотр изображения"}
                    className="fixed inset-0 z-50 bg-foreground/70 backdrop-blur-sm flex items-center justify-center p-4 cursor-zoom-out"
                    onClick={() => setOpen(false)}
                >
                    <img
                        src={src}
                        alt={alt ?? ""}
                        className="max-w-full max-h-full rounded-lg border border-border object-contain"
                    />
                </span>
            )}
        </>
    );
}

const markdownComponents: Components = {
    p: ({children}) => <p className="mb-2 last:mb-0">{withImageLockChips(children)}</p>,
    ul: ({children}) => <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>,
    ol: ({children}) => <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>,
    li: ({children}) => <li>{withImageLockChips(children)}</li>,
    h3: ({children}) => <h3 className="font-display text-lg font-semibold mt-3 mb-1">{children}</h3>,
    a: ({href, children}) => (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline">
            {children}
        </a>
    ),
    strong: ({children}) => <strong className="font-semibold">{children}</strong>,
    em: ({children}) =>
        typeof children === "string" && LOCK_TEASER.test(children) ? (
            <LockChip />
        ) : (
            <em className="italic text-muted-foreground">{children}</em>
        ),
    img: ({src, alt}) => <MarkdownImage src={src} alt={alt} />,
    code: ({children}) => (
        <code className="bg-muted px-1 py-0.5 rounded text-[0.85em]">{children}</code>
    ),
    // Records tables are wide (7 cols on full tier). Wrap cells so the chat
    // panel never gains a page-level horizontal scrollbar; keep a contained
    // overflow only as a last resort for pathological unbroken tokens.
    table: ({children}) => (
        <div className="my-2 max-w-full min-w-0 overflow-x-auto">
            <table className="w-full min-w-0 border-collapse text-sm">{children}</table>
        </div>
    ),
    th: ({children}) => (
        <th className="border border-border bg-muted/60 px-2 py-1.5 text-left font-semibold align-top break-words [overflow-wrap:anywhere]">
            {children}
        </th>
    ),
    td: ({children}) => (
        <td className="border border-border px-2 py-1.5 align-top break-words [overflow-wrap:anywhere]">
            {children}
        </td>
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

function PaywallCTA() {
    const openPaywall = useOpenPaywall();
    return (
        <button
            type="button"
            onClick={openPaywall}
            className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-full px-3 py-1.5 hover:bg-accent/90 transition-colors cursor-pointer"
        >
            Оформить тариф
        </button>
    );
}

export function ChatMessageBubble({message}: { message: DisplayMessage }) {
    const isUser = message.role === "user";

    return (
        <div className={cn("flex w-full min-w-0", isUser ? "justify-end" : "justify-start")}>
            <div
                className={cn(
                    "min-w-0 flex flex-col gap-1",
                    // Assistant answers (often with records tables) use the full
                    // reading column; user bubbles stay narrower and right-aligned.
                    isUser ? "max-w-[85%] md:max-w-[75%] items-end" : "w-full max-w-full",
                )}
            >
                {!isUser && (message.steps || message.searchlog) && (
                    <StepsBlock
                        steps={message.steps ?? []}
                        searchlog={message.searchlog}
                        live={message.live}
                    />
                )}
                <div
                    className={cn(
                        "min-w-0 max-w-full rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-xs",
                        isUser
                            ? "bg-accent text-accent-foreground rounded-br-md whitespace-pre-wrap"
                            : "bg-secondary text-secondary-foreground rounded-bl-md",
                        message.error && "bg-destructive/10 text-destructive border border-destructive/30",
                    )}
                >
                    {message.pending ? (
                        <TypingIndicator />
                    ) : isUser ? (
                        <>
                            {message.scans && message.scans.length > 0 && (
                                <span className="flex flex-wrap justify-end gap-2 mb-2">
                                    {message.scans.map((scan) => (
                                        <span
                                            key={`${scan.previewUrl}-${scan.fileName}`}
                                            className="inline-flex items-center gap-1.5 rounded-lg bg-background/20 px-2 py-1"
                                        >
                                            <img
                                                src={scan.previewUrl}
                                                alt=""
                                                className="w-8 h-8 rounded object-cover"
                                            />
                                            <span className="text-xs max-w-[140px] truncate">
                                                {scan.fileName}
                                            </span>
                                        </span>
                                    ))}
                                </span>
                            )}
                            {message.content}
                        </>
                    ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{message.content}</ReactMarkdown>
                    )}
                    {message.capped && !message.error && (
                        <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground bg-background/60 border border-border rounded-full px-2.5 py-1">
                            <AlertTriangle className="w-3 h-3" />
                            Ответ сокращён — лимит сложной задачи
                        </div>
                    )}
                    {message.error && message.paywallAction && (
                        <PaywallCTA />
                    )}
                </div>
            </div>
        </div>
    );
}
