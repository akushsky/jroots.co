import {useNavigate} from "react-router-dom";
import {jwtDecode} from "jwt-decode"; // we’ll need to install this
import {useState, useEffect} from "react";
import {Input} from "@/components/ui/input";
import {Card, CardContent} from "@/components/ui/card";
import {searchObjects} from "../api/api";
import Highlighter from "react-highlight-words";
import {Button} from "@/components/ui/button.tsx";
import {Tooltip, TooltipContent, TooltipProvider, TooltipTrigger} from "@/components/ui/tooltip.tsx";
import {getPaginationPages} from "@/api/paginate.ts";

interface ImageSource {
    id: number;
    source_name: string;
}

interface SearchResult {
    id: number;
    text_content: string;
    image_url: string;
    thumbnail_url: string;
    image_path: string;
    similarity_score: number;
    image: { image_key: string, image_path: string, source: ImageSource, sha512_hash: string };
}

export default function SearchPage() {
    const navigate = useNavigate();
    const [user, setUser] = useState<{ email: string } | null>(null);
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [popupImage, setPopupImage] = useState<string | null>(null);
    const [isZoomed, setIsZoomed] = useState(false);

    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const pageSize = 20;

    useEffect(() => {
        setPage(0);
    }, [query]);

    useEffect(() => {
        const token = localStorage.getItem("token");
        if (token) {
            try {
                const decoded: any = jwtDecode(token);
                setUser({email: decoded.sub});
            } catch {
                setUser(null);
            }
        }
    }, []);

    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                setPopupImage(null);
                setIsZoomed(false);
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    useEffect(() => {
        const delay = setTimeout(async () => {
            if (query.trim()) {
                const res = await searchObjects(query, page, pageSize);
                setResults(res.items);
                setTotal(res.total);
            } else {
                setResults([]);
                setTotal(0)
            }
        }, 300);

        return () => clearTimeout(delay);
    }, [query, page]);

    const pageCount = Math.ceil(total / pageSize);
    const visiblePages = getPaginationPages(page, pageCount);

    return (
        <div className="max-w-3xl mx-auto mt-10">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-xl font-semibold">Ревизия внезапных евреев</h1>
                {user ? (
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        Вы вошли как: <span className="font-medium">{user.email}</span>
                        <Button
                            variant="outline"
                            onClick={() => {
                                localStorage.removeItem("token");
                                setUser(null);
                            }}
                        >
                            Выйти
                        </Button>
                    </div>
                ) : (
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={() => navigate("/login")}>Вход</Button>
                        <Button onClick={() => navigate("/register")}>Регистрация</Button>
                    </div>
                )}
            </div>

            <Input
                placeholder="Поиск..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
            />

            <div className="mt-6 grid gap-4">
                {results.map((result) => (
                    <Card key={result.id}>
                        <div className="relative">
                            <CardContent className="flex gap-4 items-center p-4">
                                <img
                                    src={`${result.thumbnail_url}`}
                                    alt="result"
                                    className="w-20 h-20 object-cover rounded cursor-pointer"
                                    onClick={() => setPopupImage(result.image_url)}
                                />
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
                                            <TooltipProvider>
                                                <Tooltip>
                                                    <TooltipTrigger asChild>
                                                        <span
                                                            className="italic cursor-help underline decoration-dotted mr-1">
                                                            Шифр дела скрыт
                                                        </span>
                                                    </TooltipTrigger>
                                                    <TooltipContent>
                                                        <p>Подпишитесь, чтобы получить доступ к шифру дела</p>
                                                    </TooltipContent>
                                                </Tooltip>
                                            </TooltipProvider>
                                        ) : (
                                            <Highlighter
                                                searchWords={[query]}
                                                autoEscape
                                                textToHighlight={result.image.image_path + " "}
                                            />
                                        )}
                                        <Highlighter
                                            searchWords={[query]}
                                            autoEscape
                                            textToHighlight={`(${result.image?.source?.source_name}) ${result.image?.image_key}`}
                                        />
                                    </div>

                                </div>
                            </CardContent>
                            {result.similarity_score !== undefined && (
                                <div
                                    className="absolute top-2 right-2 bg-green-600 text-white text-xs px-2 py-1 rounded-full shadow">
                                    {result.similarity_score}%
                                </div>
                            )}
                        </div>
                    </Card>
                ))}

                {results.length === 0 && query.trim() && (
                    <div className="text-center text-gray-500 py-6">
                        Нет результатов по запросу «{query}»
                    </div>
                )}

                <div className="flex justify-center gap-2 mt-4 flex-wrap">
                    {visiblePages.map((p, idx) =>
                        p === 'ellipsis' ? (
                            <span key={`ellipsis-${idx}`} className="px-2 text-gray-400">…</span>
                        ) : (
                            <Button
                                key={p}
                                variant={p === page ? "default" : "outline"}
                                onClick={() => setPage(p)}
                            >
                                {p + 1}
                            </Button>
                        )
                    )}
                </div>
            </div>
            {popupImage && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
                    onClick={() => {
                        setPopupImage(null);
                        setIsZoomed(false);
                    }}
                >
                    <div
                        className={`max-w-full max-h-full ${isZoomed ? 'overflow-auto' : 'overflow-hidden'}`}
                        onClick={(e) => e.stopPropagation()} // prevent close on image click
                    >
                        <img
                            src={`${popupImage}`}
                            alt="Popup"
                            className={`transition-all duration-300 shadow-2xl rounded ${
                                isZoomed ? 'cursor-zoom-out' : 'cursor-zoom-in'
                            }`}
                            style={{
                                width: isZoomed ? 'auto' : '100%',
                                height: isZoomed ? 'auto' : 'auto',
                                maxWidth: isZoomed ? 'none' : '100vw',
                                maxHeight: isZoomed ? 'none' : '100vh',
                                display: 'block',
                            }}
                            onClick={() => setIsZoomed((z) => !z)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
