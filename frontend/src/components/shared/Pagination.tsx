import {Button} from "@/components/ui/button";
import {getPaginationPages} from "@/api/paginate";

interface PaginationProps {
    page: number;
    totalPages: number;
    onPageChange: (page: number) => void;
}

export function Pagination({page, totalPages, onPageChange}: PaginationProps) {
    const visiblePages = getPaginationPages(page, totalPages);

    if (totalPages <= 1) return null;

    return (
        <div className="flex justify-center gap-2 mt-4 flex-wrap">
            {visiblePages.map((p, idx) =>
                p === "ellipsis" ? (
                    <span key={`ellipsis-${idx}`} className="px-2 text-gray-400">
                        &hellip;
                    </span>
                ) : (
                    <Button
                        key={p}
                        variant={p === page ? "default" : "outline"}
                        onClick={() => onPageChange(p)}
                        aria-current={p === page ? "page" : undefined}
                    >
                        {p + 1}
                    </Button>
                ),
            )}
        </div>
    );
}
