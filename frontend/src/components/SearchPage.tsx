import {useState, useEffect} from "react";
import {Input} from "@/components/ui/input";
import {Card, CardContent} from "@/components/ui/card";
import {apiClient, searchObjects} from "../api/api";

interface ImageSource {
    id: number;
    source_name: string;
}

interface SearchResult {
    id: number;
    text_content: string;
    image_url: string;
    thumbnail_url : string;
    image_path: string;
    image: { image_key: string, sha512_hash: string };
}

export default function SearchPage() {
    const [query, setQuery] = useState("");
    const [imageSources, setImageSources] = useState<ImageSource[]>([]);
    const [results, setResults] = useState<SearchResult[]>([]);
    const [popupImage, setPopupImage] = useState<string | null>(null);

    const fetchSources = () => apiClient.get("/admin/image-sources").then(res => setImageSources(res.data));

    useEffect(() => {
        fetchSources();

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
                        <CardContent className="flex gap-4 items-center p-4">
                            <img
                                src={`http://localhost:8000${result.image_url}`}
                                alt="result"
                                className="w-20 h-20 object-cover rounded cursor-pointer"
                                onClick={() => setPopupImage(result.image_url)}
                            />
                            <div>
                                <p className="text-sm text-muted-foreground">
                                    {result.image_path} ({imageSources.find(src => src.id === parseInt(result.image?.image_key))?.source_name || ""})
                                </p>
                                <p>{result.text_content}</p>
                            </div>
                        </CardContent>
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
