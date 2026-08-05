import {useEffect, useState} from "react";
import {ChevronRight} from "lucide-react";
import {Collapsible, CollapsibleContent, CollapsibleTrigger} from "@/components/ui/collapsible";
import {cn} from "@/lib/utils";

interface StepsBlockProps {
    steps: string[];
    /** Agent's search journal lines («Проверенные базы»), rendered after the steps. */
    searchlog?: string[];
    /** True while the owning message is still streaming — accordion stays open and live. */
    live?: boolean;
}

export function StepsBlock({steps, searchlog, live = false}: StepsBlockProps) {
    const [open, setOpen] = useState(live);

    // Open while the stream is live, collapse back to the default once it ends.
    useEffect(() => {
        setOpen(live);
    }, [live]);

    const items = steps.map((step) => step.trim()).filter(Boolean);
    const logLines = (searchlog ?? []).map((line) => line.trim()).filter(Boolean);

    if (items.length === 0 && logLines.length === 0) return null;

    return (
        <Collapsible open={open} onOpenChange={setOpen} data-testid="steps-block">
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
                <ChevronRight
                    className={cn("w-3 h-3 transition-transform", open && "rotate-90")}
                />
                Ход поиска
                {live && (
                    <span className="inline-flex gap-0.5 ml-1">
                        {[0, 1, 2].map((i) => (
                            <span
                                key={i}
                                className="w-1 h-1 rounded-full bg-muted-foreground/70 animate-bounce"
                                style={{animationDelay: `${i * 150}ms`}}
                            />
                        ))}
                    </span>
                )}
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="mt-1 mb-1 rounded-md bg-muted/50 border border-border/60 px-3 py-2 text-xs text-muted-foreground max-h-64 overflow-y-auto">
                    {items.length > 0 && (
                        <ol className="space-y-1.5 list-none">
                            {items.map((step, index) => (
                                <li key={index} className="flex gap-2">
                                    <span className="shrink-0 text-muted-foreground/60 tabular-nums">
                                        {index + 1}.
                                    </span>
                                    <span className="whitespace-pre-wrap">{step}</span>
                                </li>
                            ))}
                        </ol>
                    )}
                    {logLines.length > 0 && (
                        <div
                            data-testid="searchlog-section"
                            className={cn(items.length > 0 && "mt-2 pt-2 border-t border-border/60")}
                        >
                            <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
                                Проверенные базы
                            </span>
                            <ul className="mt-1 space-y-0.5 font-mono text-[11px] leading-relaxed">
                                {logLines.map((line, index) => (
                                    <li key={index} className="whitespace-pre-wrap break-words">
                                        {line}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </CollapsibleContent>
        </Collapsible>
    );
}
