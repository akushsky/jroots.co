import {useCallback, useEffect, useRef, useState} from "react";
import {useNavigate} from "react-router-dom";
import {Input} from "@/components/ui/input";
import {Card, CardContent} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Tooltip, TooltipContent, TooltipProvider, TooltipTrigger} from "@/components/ui/tooltip";
import Highlighter from "react-highlight-words";
import {fetchImage, requestAccess, searchObjects} from "@/api/api";
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
    const pageSize = 20;
    const abortControllerRef = useRef<AbortController | null>(null);

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
        setPage(0);
    }, [query]);

    useEffect(() => {
        const delay = setTimeout(async () => {
            if (query.trim()) {
                abortControllerRef.current?.abort();
                const controller = new AbortController();
                abortControllerRef.current = controller;

                try {
                    const res = await searchObjects(query, page, pageSize, controller.signal);
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
    }, [query, page]);

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

    return (
        <TooltipProvider>
            <div className="max-w-3xl mx-auto mt-10">
                <div className="flex justify-between items-center mb-6 flex-wrap gap-2">
                    <h1 className="text-xl font-semibold">Ревизия внезапных евреев</h1>
                    {user ? (
                        <div className="flex items-center gap-3 text-sm text-muted-foreground">
                            <div className="text-right leading-tight">
                                <div className="text-xs text-gray-500">Вы вошли как</div>
                                <div className="font-medium">{user.username}</div>
                                <div className="text-xs">{user.email}</div>
                            </div>
                            <Button variant="outline" onClick={logout}>
                                Выйти
                            </Button>
                        </div>
                    ) : (
                        <div className="flex gap-2">
                            <Button variant="outline" onClick={() => navigate("/login")}>Вход</Button>
                            <Button onClick={() => navigate("/signup")}>Регистрация</Button>
                        </div>
                    )}
                </div>

                <Input placeholder="Поиск..." value={query} onChange={(e) => setQuery(e.target.value)} />

                <div className="mt-6 grid gap-4">
                    {results.map((result) => (
                        <Card key={result.id}>
                            <div className="relative">
                                <CardContent className="flex gap-4 items-center p-4">
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <img
                                                src={result.thumbnail_url}
                                                alt={result.text_content}
                                                className={`w-20 h-20 object-cover rounded cursor-pointer ${user?.is_verified ? "" : "opacity-60"}`}
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
                                    <div>
                                        <p>
                                            <Highlighter
                                                searchWords={[query]}
                                                autoEscape
                                                textToHighlight={result.text_content}
                                            />
                                        </p>
                                        <div className="text-sm text-muted-foreground">
                                            {result.image?.image_path === "********" ? (
                                                <Tooltip>
                                                    <TooltipTrigger asChild>
                                                        <span className="italic cursor-help underline decoration-dotted mr-1">
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
                                                    textToHighlight={(result.image?.image_path ?? "") + " "}
                                                />
                                            )}
                                            <Highlighter
                                                searchWords={[query]}
                                                autoEscape
                                                textToHighlight={`(${result.image?.source?.source_name ?? ""}) ${result.image?.image_key ?? ""}`}
                                            />
                                        </div>
                                    </div>
                                </CardContent>
                                <div className="absolute top-2 right-2 z-10">
                                    {result.requested ? (
                                        <div className="bg-green-600 text-white text-xs px-3 py-1 rounded-full shadow flex items-center gap-1">
                                            Запрос отправлен
                                        </div>
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
                    ))}

                    {results.length === 0 && query.trim() && (
                        <div className="text-center text-gray-500 py-6">
                            Нет результатов по запросу &laquo;{query}&raquo;
                        </div>
                    )}

                    <Pagination page={page} totalPages={pageCount} onPageChange={setPage} />
                </div>

                {isLoadingPopup && <LoadingOverlay message="Загрузка изображения..." />}
                <ImagePopup imageUrl={popupImage} onClose={() => setPopupImage(null)} />

                {successMessage && (
                    <div className="text-green-600 text-center font-medium mt-4">{successMessage}</div>
                )}
            </div>
        </TooltipProvider>
    );
}
