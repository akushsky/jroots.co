import {useCallback, useEffect, useRef, useState} from "react";
import {useNavigate} from "react-router-dom";
import {Search} from "lucide-react";
import {AnimatePresence, motion} from "motion/react";
import {Input} from "@/components/ui/input";
import {Card, CardContent} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Tooltip, TooltipContent, TooltipProvider, TooltipTrigger} from "@/components/ui/tooltip";
import {Collapsible, CollapsibleContent, CollapsibleTrigger} from "@/components/ui/collapsible";
import {Select, SelectContent, SelectItem, SelectTrigger, SelectValue} from "@/components/ui/select";
import Highlighter from "react-highlight-words";
import {fetchImage, fetchSources, requestAccess, searchObjects} from "@/api/api";
import {useAuth} from "@/hooks/useAuth";
import {ImagePopup} from "@/components/shared/ImagePopup";
import {LoadingOverlay} from "@/components/shared/LoadingOverlay";
import {Pagination} from "@/components/shared/Pagination";

interface ImageSource {
    id: number;
    source_name: string;
}

interface SearchResult {
    id: number;
    text_content: string;
    image_id: number;
    thumbnail_url: string;
    similarity_score: number;
    image: {
        id: number;
        image_key: string;
        image_path: string;
        source: ImageSource | null;
        sha512_hash: string;
    } | null;
    requested?: boolean;
}

const EXAMPLE_SEARCHES = ["Рабинович", "Зильберштейн", "Бердичев", "Житомир"];

export default function SearchPage() {
    const navigate = useNavigate();
    const {user, logout} = useAuth();
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [popupImage, setPopupImage] = useState<string | null>(null);
    const [isLoadingPopup, setIsLoadingPopup] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const [sources, setSources] = useState<Array<{ id: number; source_name: string; description: string | null }>>([]);
    const [sourceId, setSourceId] = useState<number | undefined>(undefined);
    const [sortBy, setSortBy] = useState<"relevance" | "date">("relevance");
    const [searchMode, setSearchMode] = useState<"fuzzy" | "exact">("fuzzy");
    const [filtersOpen, setFiltersOpen] = useState(false);
    const pageSize = 20;
    const abortControllerRef = useRef<AbortController | null>(null);

    const activeFilterCount = [
        sourceId !== undefined,
        sortBy !== "relevance",
        searchMode !== "fuzzy",
    ].filter(Boolean).length;

    const sendRequestAccess = async (result: SearchResult) => {
        if (!user) {
            setSuccessMessage("Пожалуйста, войдите, чтобы отправить запрос.");
            setTimeout(() => setSuccessMessage(null), 5000);
            return;
        }

        try {
            await requestAccess(result.image_id, result.text_content);
            setSuccessMessage("Запрос успешно отправлен администратору.");
            setResults((prev) =>
                prev.map((r) => (r.id === result.id ? {...r, requested: true} : r)),
            );
        } catch {
            setSuccessMessage("Произошла ошибка при отправке запроса.");
        }

        setTimeout(() => setSuccessMessage(null), 5000);
    };

    useEffect(() => {
        fetchSources().then(setSources).catch(() => {});
    }, []);

    useEffect(() => {
        setPage(0);
    }, [query, sourceId, sortBy, searchMode]);

    useEffect(() => {
        const delay = setTimeout(async () => {
            if (query.trim()) {
                abortControllerRef.current?.abort();
                const controller = new AbortController();
                abortControllerRef.current = controller;

                try {
                    const res = await searchObjects(query, page, pageSize, controller.signal, {
                        source_id: sourceId,
                        sort: sortBy,
                        mode: searchMode,
                    });
                    setResults(res.items);
                    setTotal(res.total);
                } catch (err: unknown) {
                    if (err instanceof Error && err.name !== "CanceledError") {
                        setResults([]);
                        setTotal(0);
                    }
                }
            } else {
                setResults([]);
                setTotal(0);
            }
        }, 300);

        return () => clearTimeout(delay);
    }, [query, page, sourceId, sortBy, searchMode]);

    const handleImageClick = useCallback(
        async (imageId: number) => {
            if (!user?.is_verified) return;
            setIsLoadingPopup(true);
            const blobUrl = await fetchImage(imageId);
            if (blobUrl) setPopupImage(blobUrl);
            setIsLoadingPopup(false);
        },
        [user],
    );

    const pageCount = Math.ceil(total / pageSize);
    const showEmptyState = !query.trim() && results.length === 0;

    return (
        <TooltipProvider>
            <div className="max-w-3xl mx-auto px-4">
                {/* Header */}
                <div className="flex justify-between items-start mb-8 flex-wrap gap-4">
                    <div>
                        <h1 className="text-4xl font-bold tracking-tight">
                            JRoots
                        </h1>
                        <p className="text-muted-foreground mt-1 text-sm">
                            Поиск по еврейским архивным материалам
                        </p>
                    </div>
                    {user ? (
                        <div className="flex items-center gap-3 text-sm text-muted-foreground">
                            <div className="text-right leading-tight">
                                <div className="font-medium text-foreground">{user.username}</div>
                                <div className="text-xs">{user.email}</div>
                            </div>
                            <Button variant="outline" size="sm" onClick={logout}>
                                Выйти
                            </Button>
                        </div>
                    ) : (
                        <div className="flex gap-2">
                            <Button variant="outline" size="sm" onClick={() => navigate("/login")}>Вход</Button>
                            <Button size="sm" onClick={() => navigate("/signup")}>Регистрация</Button>
                        </div>
                    )}
                </div>

                <div className="border-b border-border mb-6" />

                {/* Search input */}
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground pointer-events-none" />
                    <Input
                        placeholder="Введите фамилию, имя или название документа..."
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        className="h-12 text-base pl-11 bg-card"
                    />
                </div>

                {/* Filters */}
                <div className="mt-3">
                    <Collapsible open={filtersOpen} onOpenChange={setFiltersOpen}>
                        <CollapsibleTrigger asChild>
                            <Button variant="outline" size="sm" className="gap-2">
                                Фильтры
                                {activeFilterCount > 0 && (
                                    <span className="bg-accent text-accent-foreground text-xs rounded-full px-1.5 py-0.5 min-w-5 text-center">
                                        {activeFilterCount}
                                    </span>
                                )}
                            </Button>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="mt-3 p-4 border rounded-lg space-y-4 bg-card">
                            <div className="space-y-1">
                                <label className="text-sm font-medium">Архив</label>
                                <Select
                                    value={sourceId !== undefined ? String(sourceId) : "all"}
                                    onValueChange={(v) => setSourceId(v === "all" ? undefined : Number(v))}
                                >
                                    <SelectTrigger className="w-full">
                                        <SelectValue placeholder="Все архивы" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="all">Все архивы</SelectItem>
                                        {sources.map((s) => (
                                            <SelectItem key={s.id} value={String(s.id)}>
                                                {s.source_name}{s.description ? ` (${s.description})` : ""}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-1">
                                <label className="text-sm font-medium">Сортировка</label>
                                <div className="flex gap-2">
                                    <Button
                                        variant={sortBy === "relevance" ? "default" : "outline"}
                                        size="sm"
                                        onClick={() => setSortBy("relevance")}
                                    >
                                        По релевантности
                                    </Button>
                                    <Button
                                        variant={sortBy === "date" ? "default" : "outline"}
                                        size="sm"
                                        onClick={() => setSortBy("date")}
                                    >
                                        По дате
                                    </Button>
                                </div>
                            </div>

                            <div className="space-y-1">
                                <label className="text-sm font-medium">Режим поиска</label>
                                <div className="flex gap-2">
                                    <Button
                                        variant={searchMode === "fuzzy" ? "default" : "outline"}
                                        size="sm"
                                        onClick={() => setSearchMode("fuzzy")}
                                    >
                                        Нечёткий
                                    </Button>
                                    <Button
                                        variant={searchMode === "exact" ? "default" : "outline"}
                                        size="sm"
                                        onClick={() => setSearchMode("exact")}
                                    >
                                        Точный
                                    </Button>
                                </div>
                            </div>
                        </CollapsibleContent>
                    </Collapsible>
                </div>

                {/* Empty state */}
                {showEmptyState && (
                    <motion.div
                        initial={{opacity: 0, y: 8}}
                        animate={{opacity: 1, y: 0}}
                        transition={{duration: 0.4}}
                        className="text-center py-16"
                    >
                        <p className="text-muted-foreground mb-6">
                            Единая база данных по архивным материалам еврейских общин
                        </p>
                        <div className="flex flex-wrap justify-center gap-2">
                            {EXAMPLE_SEARCHES.map((term) => (
                                <button
                                    key={term}
                                    onClick={() => setQuery(term)}
                                    className="px-4 py-1.5 text-sm rounded-full border border-border bg-card hover:bg-accent hover:text-accent-foreground transition-colors"
                                >
                                    {term}
                                </button>
                            ))}
                        </div>
                    </motion.div>
                )}

                {/* Results */}
                <div className="mt-4 grid gap-3">
                    {total > 0 && (
                        <p className="text-sm text-muted-foreground">
                            {total} {(() => {
                                const n = total % 100;
                                const d = total % 10;
                                if (n >= 11 && n <= 19) return "результатов";
                                if (d === 1) return "результат";
                                if (d >= 2 && d <= 4) return "результата";
                                return "результатов";
                            })()}
                        </p>
                    )}
                    <AnimatePresence>
                        {results.map((result, i) => (
                            <motion.div
                                key={result.id}
                                initial={{opacity: 0, y: 6}}
                                animate={{opacity: 1, y: 0}}
                                transition={{duration: 0.25, delay: i * 0.03}}
                            >
                                <Card className="overflow-hidden hover:shadow-md transition-shadow">
                                    <div className="relative">
                                        <CardContent className="flex gap-4 items-start p-4">
                                            <Tooltip>
                                                <TooltipTrigger asChild>
                                                    <img
                                                        src={result.thumbnail_url}
                                                        alt={result.text_content}
                                                        className={`w-16 h-16 object-cover rounded border border-border shrink-0 cursor-pointer ${user?.is_verified ? "" : "opacity-50"}`}
                                                        onClick={() => result.image_id && handleImageClick(result.image_id)}
                                                    />
                                                </TooltipTrigger>
                                                {!user ? (
                                                    <TooltipContent>
                                                        <p>Войдите или зарегистрируйтесь, чтобы открыть полное изображение</p>
                                                    </TooltipContent>
                                                ) : !user.is_verified ? (
                                                    <TooltipContent>
                                                        <p>Подтвердите свою учетную запись, чтобы открыть полное изображение</p>
                                                    </TooltipContent>
                                                ) : null}
                                            </Tooltip>
                                            <div className="min-w-0 flex-1">
                                                <p className="font-semibold text-lg font-[family-name:var(--font-display)]">
                                                    <Highlighter
                                                        searchWords={[query]}
                                                        autoEscape
                                                        textToHighlight={result.text_content}
                                                    />
                                                </p>
                                                <div className="text-sm text-muted-foreground mt-1 space-y-0.5">
                                                    <div>
                                                        {result.image?.image_path === "********" ? (
                                                            <Tooltip>
                                                                <TooltipTrigger asChild>
                                                                    <span className="italic cursor-help underline decoration-dotted">
                                                                        Шифр дела скрыт
                                                                    </span>
                                                                </TooltipTrigger>
                                                                <TooltipContent>
                                                                    <p>Запросите доступ, чтобы увидеть шифр</p>
                                                                </TooltipContent>
                                                            </Tooltip>
                                                        ) : (
                                                            <Highlighter
                                                                searchWords={[query]}
                                                                autoEscape
                                                                textToHighlight={result.image?.image_path ?? ""}
                                                            />
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        {result.image?.source && (
                                                            <span className="inline-block text-xs px-2 py-0.5 rounded bg-secondary text-secondary-foreground">
                                                                {result.image.source.source_name}
                                                            </span>
                                                        )}
                                                        <Highlighter
                                                            searchWords={[query]}
                                                            autoEscape
                                                            textToHighlight={result.image?.image_key ?? ""}
                                                            className="text-xs"
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        </CardContent>
                                        <div className="absolute top-3 right-3">
                                            {result.requested ? (
                                                <span className="text-xs px-3 py-1 rounded-full bg-accent text-accent-foreground">
                                                    Запрос отправлен
                                                </span>
                                            ) : (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    className="text-xs px-3 py-1 h-auto rounded-full"
                                                    onClick={() => sendRequestAccess(result)}
                                                >
                                                    Запросить доступ
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                </Card>
                            </motion.div>
                        ))}
                    </AnimatePresence>

                    {results.length === 0 && query.trim() && (
                        <div className="text-center text-muted-foreground py-10">
                            Нет результатов по запросу &laquo;{query}&raquo;
                        </div>
                    )}

                    <Pagination page={page} totalPages={pageCount} onPageChange={setPage} />
                </div>

                {isLoadingPopup && <LoadingOverlay message="Загрузка изображения..." />}
                <ImagePopup imageUrl={popupImage} onClose={() => setPopupImage(null)} />

                {successMessage && (
                    <div className="text-center font-medium mt-4 text-sm text-accent">
                        {successMessage}
                    </div>
                )}
            </div>
        </TooltipProvider>
    );
}
