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
        <div className="flex flex-col h-full">
            <div className="p-3 border-b border-border flex items-center gap-2">
                <Button onClick={onNew} variant="outline" className="flex-1">
                    <MessageSquarePlus />
                    Новый поиск
                </Button>
                {onClose && (
                    <Button onClick={onClose} variant="ghost" size="icon" className="md:hidden" aria-label="Закрыть список">
                        <X />
                    </Button>
                )}
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
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
                            "w-full text-left rounded-md px-3 py-2 text-sm transition-colors",
                            session.id === activeId
                                ? "bg-accent text-accent-foreground"
                                : "hover:bg-muted",
                        )}
                    >
                        <span className="block truncate font-medium">
                            {sessionDisplayTitle(session)}
                        </span>
                        <span
                            className={cn(
                                "block text-xs mt-0.5",
                                session.id === activeId ? "text-accent-foreground/70" : "text-muted-foreground",
                            )}
                        >
                            {formatDate(session.created_at)}
                        </span>
                    </button>
                ))}
            </div>
        </div>
    );
}
