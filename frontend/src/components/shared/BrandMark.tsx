import {Link} from "react-router-dom";
import {cn} from "@/lib/utils";

interface BrandMarkProps {
    /** `start` sits in a header row next to actions; `center` stacks above auth cards. */
    align?: "center" | "start";
    className?: string;
}

/** Brand + way home for surfaces that carry no AppHeader (auth forms, landing). */
export function BrandMark({align = "center", className}: BrandMarkProps) {
    const inline = align === "start";
    return (
        <Link to="/" className={cn("group block", inline ? "min-w-0" : "text-center", className)}>
            <span className="block font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight leading-none transition-colors group-hover:text-accent">
                JRoots
            </span>
            <span className={cn("mt-1.5 block text-sm text-muted-foreground", inline && "truncate")}>
                Поиск по еврейским архивным материалам
            </span>
        </Link>
    );
}
