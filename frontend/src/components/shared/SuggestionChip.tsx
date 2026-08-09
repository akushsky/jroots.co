import type {ReactNode} from "react";
import {cn} from "@/lib/utils";

interface SuggestionChipProps {
    onClick: () => void;
    className?: string;
    children: ReactNode;
}

/** Clickable example query — used by the search and chat empty states alike. */
export function SuggestionChip({onClick, className, children}: SuggestionChipProps) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "rounded-full border border-border bg-secondary/50 px-4 py-1.5 text-sm",
                "transition-colors hover:border-accent hover:bg-accent hover:text-accent-foreground",
                "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                className,
            )}
        >
            {children}
        </button>
    );
}
