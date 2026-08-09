import type {ReactNode} from "react";
import {cn} from "@/lib/utils";

type Measure = "reading" | "workspace";

interface PageContainerProps {
    /**
     * Outer shell width. Authenticated product pages (Search, Chat) should use
     * `workspace` so the shared AppHeader does not jump when switching tabs.
     * Inner reading measure is applied by the page itself (`max-w-reading`).
     */
    measure?: Measure;
    className?: string;
    children: ReactNode;
}

/**
 * The one place page width and gutters are decided. Tokens live in index.css.
 */
export function PageContainer({measure = "workspace", className, children}: PageContainerProps) {
    return (
        <div
            className={cn(
                "mx-auto w-full px-4 sm:px-6",
                measure === "reading" ? "max-w-reading" : "max-w-workspace",
                className,
            )}
        >
            {children}
        </div>
    );
}
