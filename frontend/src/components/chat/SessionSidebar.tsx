import {MessageSquarePlus, X} from "lucide-react";
import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import type {ChatSessionSummary} from "@/api/chat";
import {sessionDisplayTitle} from "./sessionTitle";

interface SessionSidebarProps {
    sessions: ChatSessionSummary[];
    activeId: string | null;
    onSelect: (id: string) => void;
    onNew: () => void;
    onClose?: () => void;
}

function formatDate(iso: string): string {
    const date = new Date(iso);
    return Number.isNaN(date.getTime())
        ? ""
        : date.toLocaleDateString("ru-RU", {day: "numeric", month: "short"});
}

export function SessionSidebar({sessions, activeId, onSelect, onNew, onClose}: SessionSidebarProps) {
    return (
        <div className="flex flex-col h-full min-w-0 overflow-hidden">
            <div className="min-h-14 px-3 py-2.5 border-b border-border flex items-center gap-2 min-w-0">
                <Button onClick={onNew} variant="outline" size="sm" className="flex-1 min-w-0">
                    <MessageSquarePlus />
                    <span className="truncate">Новый поиск</span>
                </Button>
                {onClose && (
                    <Button onClick={onClose} variant="ghost" size="icon" className="md:hidden" aria-label="Закрыть список">
                        <X />
                    </Button>
                )}
            </div>
            <div className="flex-1 overflow-y-auto overflow-x-hidden p-2 space-y-1 min-w-0">
                {sessions.length === 0 && (
                    <p className="text-xs text-muted-foreground px-2 py-4 text-center">
                        Здесь появятся ваши поиски
                    </p>
                )}
                {sessions.map((session) => (
                    <button
                        key={session.id}
                        onClick={() => onSelect(session.id)}
                        className={cn(
                            "block w-full min-w-0 overflow-hidden text-left rounded-md border-l-2 px-2.5 py-2 text-sm transition-colors",
                            session.id === activeId
                                ? "border-accent bg-secondary text-foreground"
                                : "border-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                        )}
                    >
                        <span className="block truncate font-medium">
                            {sessionDisplayTitle(session)}
                        </span>
                        <span className="block truncate text-xs mt-0.5 text-muted-foreground">
                            {formatDate(session.created_at)}
                        </span>
                    </button>
                ))}
            </div>
        </div>
    );
}
