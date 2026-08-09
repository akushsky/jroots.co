import {useCallback, useEffect, useRef, useState} from "react";
import {Link, useSearchParams} from "react-router-dom";
import {Coins, PanelLeft, ScanLine, X} from "lucide-react";
import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import {
    createSession,
    getCredits,
    getSession,
    listSessions,
    streamMessage,
    uploadScan,
    ScanUploadError,
} from "@/api/chat";
import type {CappedReason, ChatSessionSummary, Credits, DoneEvent, UsageEvent} from "@/api/chat";
import {axiosErrorDetail, ChatApiError} from "@/api/errors";
import {AppHeader} from "@/components/shared/AppHeader";
import {PageContainer} from "@/components/shared/PageContainer";
import {SuggestionChip} from "@/components/shared/SuggestionChip";
import {SessionSidebar} from "./SessionSidebar";
import {ChatMessageBubble} from "./ChatMessageBubble";
import {ChatInput} from "./ChatInput";
import {Paywall} from "./Paywall";
import {PaywallContext} from "./PaywallContext";
import {chatErrorForCode, GENERIC_SEND_ERROR, GENERIC_SESSION_ERROR} from "./errorMessages";
import {extractSearchlog, extractSteps} from "./steps";
import type {ScanAttachment} from "./scans";
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
    const [paywallOpen, setPaywallOpen] = useState(false);
    const openPaywall = useCallback(() => setPaywallOpen(true), []);
    const [attachments, setAttachments] = useState<ScanAttachment[]>([]);
    const [searchParams] = useSearchParams();
    // Landing hand-off: /chat?q=... prefills the first message.
    const initialQuery = searchParams.get("q") ?? undefined;
    // ChatInput owns its draft; remounting it is how the hints prefill the field.
    const [draft, setDraft] = useState<string | undefined>(initialQuery);
    const [draftKey, setDraftKey] = useState(0);

    const applyHint = useCallback((hint: string) => {
        setDraft(hint);
        setDraftKey((key) => key + 1);
    }, []);

    const scrollRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    const patchAttachment = useCallback((localId: string, patch: Partial<ScanAttachment>) => {
        setAttachments((prev) => prev.map((a) => (a.localId === localId ? {...a, ...patch} : a)));
    }, []);

    const clearAttachments = useCallback(() => {
        setAttachments((prev) => {
            for (const a of prev) URL.revokeObjectURL(a.previewUrl);
            return [];
        });
    }, []);

    const removeAttachment = useCallback((localId: string) => {
        setAttachments((prev) => {
            const target = prev.find((a) => a.localId === localId);
            if (target) URL.revokeObjectURL(target.previewUrl);
            return prev.filter((a) => a.localId !== localId);
        });
    }, []);

    useEffect(() => {
        let cancelled = false;
        // Capture at mount: landing hand-off (/chat?q=...) means "start a new
        // search", not "dump this into the previous session".
        const landingQuery = initialQuery;
        Promise.all([listSessions(), getCredits()])
            .then(([sessionList, creditBalance]) => {
                if (cancelled) return;
                setSessions(sessionList);
                setCredits(creditBalance);
                if (landingQuery) {
                    // Fresh composer: activeId stays null until the first send
                    // creates a session. List of past sessions remains in the rail.
                    setActiveId(null);
                    setMessages([]);
                    return;
                }
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
        clearAttachments();
        try {
            const session = await getSession(id);
            setMessages(
                session.messages.map((m) => {
                    if (m.role === "assistant") {
                        const {steps, content: withoutSteps} = extractSteps(m.content);
                        const {lines, rest} = extractSearchlog(withoutSteps);
                        return {
                            id: m.id,
                            role: m.role,
                            content: rest,
                            steps: steps ?? undefined,
                            searchlog: lines.length > 0 ? lines : undefined,
                        };
                    }
                    return {id: m.id, role: m.role, content: m.content};
                }),
            );
        } catch {
            setMessages([
                {id: nextTempId(), role: "assistant", content: "Не удалось загрузить диалог", error: true},
            ]);
        }
    }, [clearAttachments]);

    const startNewSearch = useCallback(() => {
        abortRef.current?.abort();
        setActiveId(null);
        setMessages([]);
        setSessionTokens(null);
        setSidebarOpen(false);
        clearAttachments();
    }, [clearAttachments]);

    const attachScan = useCallback(
        async (file: File) => {
            const localId = nextTempId();
            const previewUrl = URL.createObjectURL(file);
            setAttachments((prev) => [
                ...prev,
                {localId, fileName: file.name, previewUrl, status: "uploading"},
            ]);

            // The scans endpoint is session-scoped: materialize the session now
            // if the user attaches a file before the first message.
            let sessionId = activeId;
            if (!sessionId) {
                try {
                    const session = await createSession();
                    sessionId = session.id;
                    setSessions((prev) => [session, ...prev]);
                    setActiveId(session.id);
                } catch {
                    patchAttachment(localId, {
                        status: "error",
                        errorText: "Не удалось создать поиск. Попробуйте ещё раз.",
                    });
                    return;
                }
            }

            try {
                const result = await uploadScan(sessionId, file);
                if (result.status === "done") {
                    patchAttachment(localId, {
                        status: "done",
                        scanId: result.scan_id,
                        confidence: result.metadata?.confidence,
                    });
                    getCredits().then(setCredits).catch(() => {});
                } else {
                    // 201 with status:"error" in the body — vision pipeline failed
                    patchAttachment(localId, {
                        status: "error",
                        errorText: "Не удалось прочитать документ",
                    });
                }
            } catch (error) {
                if (error instanceof ScanUploadError && error.code === "no_scans_left") {
                    patchAttachment(localId, {status: "error", errorCode: "no_scans_left"});
                } else {
                    patchAttachment(localId, {
                        status: "error",
                        errorText:
                            error instanceof ScanUploadError
                                ? error.message
                                : "Не удалось обработать скан. Попробуйте ещё раз.",
                    });
                }
            }
        },
        [activeId, patchAttachment],
    );

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
            } catch (error) {
                const mapped = chatErrorForCode(axiosErrorDetail(error).code);
                setMessages((prev) => [
                    ...prev,
                    {
                        id: nextTempId(),
                        role: "assistant",
                        content: mapped?.text ?? GENERIC_SESSION_ERROR,
                        error: true,
                        paywallAction: mapped?.paywallAction,
                    },
                ]);
                return;
            }

            const doneScans = attachments.filter((a) => a.status === "done" && a.scanId !== undefined);
            const scanIds = doneScans.map((a) => a.scanId as number);

            const assistantId = nextTempId();
            setMessages((prev) => [
                ...prev,
                {
                    id: nextTempId(),
                    role: "user",
                    content,
                    ...(doneScans.length > 0 && {
                        scans: doneScans.map((a) => ({fileName: a.fileName, previewUrl: a.previewUrl})),
                    }),
                },
                {id: assistantId, role: "assistant", content: "", pending: true, live: true},
            ]);
            // Sent scans move into the bubble; failed/unsent ones stay editable above the input.
            if (doneScans.length > 0) {
                const sentIds = new Set(doneScans.map((a) => a.localId));
                setAttachments((prev) => prev.filter((a) => !sentIds.has(a.localId)));
            }
            setStreaming(true);

            const controller = new AbortController();
            abortRef.current = controller;

            try {
                const callbacks = {
                    onToken: (text: string) => {
                        setMessages((prev) =>
                            prev.map((m) =>
                                m.id === assistantId
                                    ? {...m, pending: false, content: m.content + text}
                                    : m,
                            ),
                        );
                    },
                    onStep: (text: string) => {
                        setMessages((prev) =>
                            prev.map((m) =>
                                m.id === assistantId
                                    ? {...m, steps: [...(m.steps ?? []), text]}
                                    : m,
                            ),
                        );
                    },
                    onUsage: (usage: UsageEvent) => setSessionTokens(usage.session_tokens_total),
                    onCapped: (reason: CappedReason) => patchAssistant(assistantId, {capped: reason}),
                    onDone: (done: DoneEvent) => {
                        setMessages((prev) =>
                            prev.map((m) =>
                                m.id === assistantId
                                    ? {
                                        ...m,
                                        id: done.message_id,
                                        pending: false,
                                        live: false,
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
                    onError: (message: string) => {
                        patchAssistant(assistantId, {
                            pending: false,
                            live: false,
                            content: message || "Что-то пошло не так. Попробуйте ещё раз.",
                            error: true,
                        });
                    },
                };
                // 4-arg form when there are no scans: backend treats a missing
                // scan_ids key and an empty array differently (validation).
                const result = scanIds.length > 0
                    ? await streamMessage(sessionId, content, callbacks, controller.signal, scanIds)
                    : await streamMessage(sessionId, content, callbacks, controller.signal);
                if (!result.finished) {
                    patchAssistant(assistantId, {pending: false, live: false, content: CONNECTION_LOST, error: true});
                }
            } catch (error) {
                if (!controller.signal.aborted) {
                    const mapped =
                        error instanceof ChatApiError ? chatErrorForCode(error.code) : null;
                    patchAssistant(assistantId, {
                        pending: false,
                        live: false,
                        content: mapped?.text ?? (error instanceof ChatApiError ? GENERIC_SEND_ERROR : CONNECTION_LOST),
                        error: true,
                        paywallAction: mapped?.paywallAction,
                    });
                }
            } finally {
                setStreaming(false);
                abortRef.current = null;
            }
        },
        [streaming, activeId, attachments, patchAssistant],
    );

    const showPaywall = credits !== null && credits.searches_left === 0 && !streaming;

    return (
        <PaywallContext.Provider value={openPaywall}>
            <PageContainer measure="workspace" className="flex h-[var(--layout-viewport)] flex-col">
                <AppHeader subtitle="Помощник по семейным архивам" className="mb-5" />

                <div className="relative flex flex-1 min-h-0 gap-4 pb-2 lg:gap-6">
                    <aside
                        className={cn(
                            "w-[var(--layout-rail)] max-w-[85vw] shrink-0 bg-card rounded-xl border border-border shadow-xs overflow-hidden",
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

                    <main className="flex-1 min-w-0 flex flex-col bg-card rounded-xl border border-border shadow-xs overflow-hidden">
                        <header className="min-h-14 flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5 border-b border-border sm:px-5">
                            <Button
                                variant="ghost"
                                size="icon"
                                className="md:hidden"
                                onClick={() => setSidebarOpen(true)}
                                aria-label="Открыть список поисков"
                            >
                                <PanelLeft />
                            </Button>
                            <span className="hidden items-center gap-2 text-sm font-medium sm:inline-flex">
                                <span
                                    aria-hidden
                                    className={cn(
                                        "size-1.5 rounded-full bg-accent",
                                        streaming && "animate-pulse",
                                    )}
                                />
                                {streaming ? "Ассистент ищет…" : "Ассистент"}
                            </span>
                            <div className="ml-auto flex items-center gap-2">
                                {sessionTokens !== null && (
                                    <span className="text-xs text-muted-foreground hidden lg:inline">
                                        Токенов в сессии: {sessionTokens.toLocaleString("ru-RU")}
                                    </span>
                                )}
                                {credits !== null && (
                                    <div className="flex items-center rounded-full border border-border bg-secondary/60 px-1 text-xs">
                                        <span className="inline-flex items-center gap-1.5 px-2 py-1">
                                            <Coins className="w-3.5 h-3.5 text-accent" />
                                            Осталось поисков: {credits.searches_left}
                                        </span>
                                        <span aria-hidden className="h-3.5 w-px bg-border" />
                                        <span className="inline-flex items-center gap-1.5 px-2 py-1">
                                            <ScanLine className="w-3.5 h-3.5 text-accent" />
                                            Сканов: {credits.scans_left}
                                        </span>
                                    </div>
                                )}
                            </div>
                        </header>

                        <div ref={scrollRef} className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden">
                            <div className="mx-auto flex min-h-full w-full max-w-reading min-w-0 flex-col gap-5 px-4 py-5 sm:px-6">
                                {loading ? (
                                    <div className="flex flex-1 items-center justify-center">
                                        <div className="animate-spin rounded-full h-8 w-8 border-2 border-foreground/20 border-t-foreground/60" />
                                    </div>
                                ) : messages.length === 0 ? (
                                    <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
                                        <h2 className="font-display text-2xl font-semibold">
                                            С чего начнём поиск?
                                        </h2>
                                        <p className="max-w-md text-muted-foreground text-sm">
                                            Напишите всё, что знаете о человеке или семье: фамилию, имена,
                                            место жительства, примерные годы. Помогу составить план поиска
                                            документов для репатриации.
                                        </p>
                                        <div className="flex flex-wrap justify-center gap-2">
                                            {HINTS.map((hint) => (
                                                <SuggestionChip
                                                    key={hint}
                                                    onClick={() => applyHint(hint)}
                                                    className="px-3 py-1 text-xs"
                                                >
                                                    {hint}
                                                </SuggestionChip>
                                            ))}
                                        </div>
                                    </div>
                                ) : (
                                    messages.map((message) => (
                                        <ChatMessageBubble key={message.id} message={message} />
                                    ))
                                )}
                            </div>
                        </div>

                        <footer className="border-t border-border px-4 py-3 sm:px-6">
                            <div className="mx-auto w-full max-w-reading">
                                {showPaywall ? (
                                    <Paywall />
                                ) : (
                                    <ChatInput
                                        key={draftKey}
                                        disabled={streaming || loading}
                                        attachments={attachments}
                                        onAttachFile={attachScan}
                                        onRemoveAttachment={removeAttachment}
                                        onSend={send}
                                        initialValue={draft}
                                    />
                                )}
                                <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground">
                                    <span>
                                        Ответы ассистента — ориентир для поиска, а не гарантия. Проверяйте архивные ссылки.
                                    </span>
                                    <Link to="/" className="text-accent hover:underline">
                                        Предпочитаете искать сами? Профессиональный поиск →
                                    </Link>
                                </div>
                            </div>
                        </footer>
                    </main>

                    {paywallOpen && (
                        <div
                            className="fixed inset-0 bg-foreground/40 backdrop-blur-sm flex justify-center items-center z-50 p-4"
                            onClick={() => setPaywallOpen(false)}
                        >
                            <div
                                role="dialog"
                                aria-label="Тарифы"
                                className="bg-card rounded-lg shadow-xl max-w-2xl w-full p-6 relative border-t-2 border-accent"
                                onClick={(e) => e.stopPropagation()}
                            >
                                <button
                                    onClick={() => setPaywallOpen(false)}
                                    className="absolute top-3 right-3 text-muted-foreground hover:text-foreground transition-colors"
                                    aria-label="Закрыть"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                                <Paywall
                                    title="Полная версия записи"
                                    description="Ссылки на источники, сканы документов и полный текст записей доступны на платных тарифах."
                                />
                            </div>
                        </div>
                    )}
                </div>
            </PageContainer>
        </PaywallContext.Provider>
    );
}
