import {useCallback, useEffect, useRef, useState} from "react";
import {Link} from "react-router-dom";
import {Coins, PanelLeft} from "lucide-react";
import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import {
    createSession,
    getCredits,
    getSession,
    listSessions,
    streamMessage,
} from "@/api/chat";
import type {ChatSessionSummary, Credits} from "@/api/chat";
import {SessionSidebar} from "./SessionSidebar";
import {ChatMessageBubble} from "./ChatMessageBubble";
import {ChatInput} from "./ChatInput";
import {Paywall} from "./Paywall";
import type {DisplayMessage} from "./types";

const CONNECTION_LOST = "Соединение прервано, попробуйте ещё раз";

const HINTS = [
    "Рабиновичи из Бердичева, конец XIX века",
    "Дед служил в армии, погиб в 1943 под Сталинградом",
    "Семья Штерн, Кишинёв, эвакуация в 1941",
];

let tempId = 0;
const nextTempId = () => `temp-${++tempId}`;

export default function ChatPage() {
    const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [messages, setMessages] = useState<DisplayMessage[]>([]);
    const [credits, setCredits] = useState<Credits | null>(null);
    const [sessionTokens, setSessionTokens] = useState<number | null>(null);
    const [streaming, setStreaming] = useState(false);
    const [loading, setLoading] = useState(true);
    const [sidebarOpen, setSidebarOpen] = useState(false);

    const scrollRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        let cancelled = false;
        Promise.all([listSessions(), getCredits()])
            .then(([sessionList, creditBalance]) => {
                if (cancelled) return;
                setSessions(sessionList);
                setCredits(creditBalance);
                if (sessionList.length > 0) {
                    selectSession(sessionList[0].id);
                }
            })
            .catch(() => {
                if (!cancelled) setLoading(false);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
            abortRef.current?.abort();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages, streaming]);

    const selectSession = useCallback(async (id: string) => {
        setActiveId(id);
        setSidebarOpen(false);
        setSessionTokens(null);
        try {
            const session = await getSession(id);
            setMessages(
                session.messages.map((m) => ({
                    id: m.id,
                    role: m.role,
                    content: m.content,
                })),
            );
        } catch {
            setMessages([
                {id: nextTempId(), role: "assistant", content: "Не удалось загрузить диалог", error: true},
            ]);
        }
    }, []);

    const startNewSearch = useCallback(() => {
        abortRef.current?.abort();
        setActiveId(null);
        setMessages([]);
        setSessionTokens(null);
        setSidebarOpen(false);
    }, []);

    const patchAssistant = useCallback((id: string, patch: Partial<DisplayMessage>) => {
        setMessages((prev) => prev.map((m) => (m.id === id ? {...m, ...patch} : m)));
    }, []);

    const send = useCallback(
        async (content: string) => {
            if (streaming) return;

            let sessionId = activeId;
            try {
                if (!sessionId) {
                    const session = await createSession();
                    sessionId = session.id;
                    // Optimistic title: backend derives it from the first message,
                    // so mirror that locally instead of showing «Новый поиск».
                    setSessions((prev) => [
                        {...session, title: session.title || content.slice(0, 80)},
                        ...prev,
                    ]);
                    setActiveId(session.id);
                }
            } catch {
                setMessages((prev) => [
                    ...prev,
                    {id: nextTempId(), role: "assistant", content: "Не удалось создать поиск. Попробуйте ещё раз.", error: true},
                ]);
                return;
            }

            const assistantId = nextTempId();
            setMessages((prev) => [
                ...prev,
                {id: nextTempId(), role: "user", content},
                {id: assistantId, role: "assistant", content: "", pending: true},
            ]);
            setStreaming(true);

            const controller = new AbortController();
            abortRef.current = controller;

            try {
                const result = await streamMessage(
                    sessionId,
                    content,
                    {
                        onToken: (text) => {
                            setMessages((prev) =>
                                prev.map((m) =>
                                    m.id === assistantId
                                        ? {...m, pending: false, content: m.content + text}
                                        : m,
                                ),
                            );
                        },
                        onUsage: (usage) => setSessionTokens(usage.session_tokens_total),
                        onCapped: (reason) => patchAssistant(assistantId, {capped: reason}),
                        onDone: (done) => {
                            setMessages((prev) =>
                                prev.map((m) =>
                                    m.id === assistantId
                                        ? {
                                            ...m,
                                            id: done.message_id,
                                            pending: false,
                                            capped: m.capped ?? (done.capped ? "token_cap" : null),
                                        }
                                        : m,
                                ),
                            );
                            getCredits().then(setCredits).catch(() => {});
                            // Sync sidebar titles/last_message with backend truth;
                            // keep local sessions the backend list doesn't know yet.
                            listSessions()
                                .then((fresh) =>
                                    setSessions((prev) => {
                                        const merged = [...fresh];
                                        for (const s of prev) {
                                            if (!fresh.some((f) => f.id === s.id)) merged.push(s);
                                        }
                                        return merged;
                                    }),
                                )
                                .catch(() => {});
                        },
                        onError: (message) => {
                            patchAssistant(assistantId, {
                                pending: false,
                                content: message || "Что-то пошло не так. Попробуйте ещё раз.",
                                error: true,
                            });
                        },
                    },
                    controller.signal,
                );
                if (!result.finished) {
                    patchAssistant(assistantId, {pending: false, content: CONNECTION_LOST, error: true});
                }
            } catch {
                if (!controller.signal.aborted) {
                    patchAssistant(assistantId, {pending: false, content: CONNECTION_LOST, error: true});
                }
            } finally {
                setStreaming(false);
                abortRef.current = null;
            }
        },
        [streaming, activeId, patchAssistant],
    );

    const showPaywall = credits !== null && credits.searches_left === 0 && !streaming;

    return (
        <div className="relative flex h-[calc(100vh-5rem)] gap-4">
            <aside
                className={cn(
                    "w-72 shrink-0 bg-card rounded-lg border border-border overflow-hidden",
                    sidebarOpen
                        ? "absolute inset-y-0 left-0 z-20 flex md:static"
                        : "hidden md:flex",
                )}
            >
                <SessionSidebar
                    sessions={sessions}
                    activeId={activeId}
                    onSelect={selectSession}
                    onNew={startNewSearch}
                    onClose={() => setSidebarOpen(false)}
                />
            </aside>
            {sidebarOpen && (
                <button
                    className="absolute inset-0 z-10 bg-foreground/20 md:hidden"
                    onClick={() => setSidebarOpen(false)}
                    aria-label="Закрыть список поисков"
                />
            )}

            <main className="flex-1 min-w-0 flex flex-col bg-card rounded-lg border border-border overflow-hidden">
                <header className="flex items-center gap-3 px-4 py-3 border-b border-border">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="md:hidden"
                        onClick={() => setSidebarOpen(true)}
                        aria-label="Открыть список поисков"
                    >
                        <PanelLeft />
                    </Button>
                    <div className="min-w-0">
                        <h1 className="font-display text-lg font-semibold truncate">
                            Помощник по семейным архивам
                        </h1>
                        <p className="text-xs text-muted-foreground hidden sm:block">
                            Расскажите, кого ищете — подскажу, где найти документы
                        </p>
                    </div>
                    <div className="ml-auto flex items-center gap-3">
                        {sessionTokens !== null && (
                            <span className="text-xs text-muted-foreground hidden md:inline">
                                Токенов в сессии: {sessionTokens.toLocaleString("ru-RU")}
                            </span>
                        )}
                        {credits !== null && (
                            <span className="inline-flex items-center gap-1.5 text-sm bg-secondary rounded-full px-3 py-1">
                                <Coins className="w-3.5 h-3.5 text-accent" />
                                Осталось поисков: {credits.searches_left}
                            </span>
                        )}
                    </div>
                </header>

                <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
                    {loading ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="animate-spin rounded-full h-8 w-8 border-2 border-foreground/20 border-t-foreground/60" />
                        </div>
                    ) : messages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto space-y-4">
                            <h2 className="font-display text-2xl font-semibold">
                                С чего начнём поиск?
                            </h2>
                            <p className="text-muted-foreground text-sm">
                                Напишите всё, что знаете о человеке или семье: фамилию, имена,
                                место жительства, примерные годы. Помогу составить план поиска
                                документов для репатриации.
                            </p>
                            <div className="flex flex-wrap justify-center gap-2">
                                {HINTS.map((hint) => (
                                    <span
                                        key={hint}
                                        className="text-xs bg-muted text-muted-foreground rounded-full px-3 py-1.5"
                                    >
                                        {hint}
                                    </span>
                                ))}
                            </div>
                        </div>
                    ) : (
                        messages.map((message) => (
                            <ChatMessageBubble key={message.id} message={message} />
                        ))
                    )}
                </div>

                <footer className="border-t border-border p-4">
                    {showPaywall ? (
                        <Paywall />
                    ) : (
                        <ChatInput disabled={streaming || loading} onSend={send} />
                    )}
                    <p className="text-xs text-muted-foreground mt-2 text-center">
                        Ответы ассистента — ориентир для поиска, а не гарантия. Проверяйте архивные ссылки.{" "}
                        <Link to="/" className="text-accent hover:underline">
                            К архивному поисковику
                        </Link>
                    </p>
                </footer>
            </main>
        </div>
    );
}
