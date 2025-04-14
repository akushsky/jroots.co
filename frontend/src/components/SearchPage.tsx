import {useState, useEffect} from "react";
import {Input} from "@/components/ui/input";
import {Card, CardContent} from "@/components/ui/card";
import {searchObjects} from "../api/api";
import Highlighter from "react-highlight-words";

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
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [popupImage, setPopupImage] = useState<string | null>(null);

    useEffect(() => {
        const delay = setTimeout(async () => {
            if (query.trim()) {
                const data = await searchObjects(query);
                setResults(data);
            } else setResults([]);
        }, 500);

        return () => clearTimeout(delay);
    }, [query]);

    return (
        <div className="max-w-3xl mx-auto mt-10">
            <Input
                placeholder="Search..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
            />

            <div className="mt-6 grid gap-4">
                {results.map((result) => (
                    <Card key={result.id}>
                        <div className="relative">
                            <CardContent className="flex gap-4 items-center p-4">
                                <img
                                    src={`http://localhost:8000${result.thumbnail_url}`}
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
                                        <Highlighter
                                            searchWords={[query]}
                                            autoEscape
                                            textToHighlight={`${result.image?.image_path} (${result.image?.source?.source_name}) ${result.image?.image_key}`}
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
            </div>
            {popupImage && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
                    onClick={() => setPopupImage(null)}
                >
                    <img
                        src={`http://localhost:8000${popupImage}`}
                        alt="Popup"
                        className="max-h-screen max-w-screen object-contain shadow-xl"
                        onClick={(e) => e.stopPropagation()}
                    />
                </div>
            )}
        </div>
    );
}
