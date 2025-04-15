import {useState, useEffect} from "react";
import {
    apiClient,
    createSearchObject,
    deleteSearchObject,
    fetchObjects,
    searchObjects,
    updateSearchObject
} from "../api/api";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {Card, CardContent} from "@/components/ui/card";
import Highlighter from "react-highlight-words";
import {getPaginationPages} from "@/api/paginate.ts";

interface ImageSource {
    id: number;
    source_name: string;
}

interface FormState {
    text_content: string;
    image_path: string;
    image_key: string;
    image_source_id: number | null;
    image_file: File | null;
    image_file_sha512?: string;
}

export default function AdminDashboard() {
    const [objects, setObjects] = useState([]);
    const [query, setQuery] = useState("");
    const [imageSources, setImageSources] = useState<ImageSource[]>([]);
    const [popupImage, setPopupImage] = useState<string | null>(null);
    const [isZoomed, setIsZoomed] = useState(false);

    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const pageSize = 20;

    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState<FormState>({
        text_content: "",
        image_path: "",
        image_key: "",
        image_source_id: null,
        image_file: null,
        image_file_sha512: "",
    });

    const fetchSources = () => apiClient.get("/admin/image-sources").then(res => setImageSources(res.data));

    useEffect(() => {
        fetchSources();
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
                setPage(0);
                const res = await searchObjects(query, page, pageSize);
                setObjects(res.items);
                setTotal(res.total);
            } else {
                const res = await fetchObjects(page, pageSize);
                setObjects(res.items);
                setTotal(res.total);
            }
        }, 300);

        return () => clearTimeout(delay);
    }, [query, page]);

    const clearForm = () => {
        setForm({
            text_content: "",
            image_path: "",
            image_key: "",
            image_source_id: null,
            image_file: null,
            image_file_sha512: "",
        });
        setEditingId(null);
    }

    const handleClone = (obj: any) => {
        setForm({
            text_content: obj.text_content,
            image_path: obj.image?.image_path || "",
            image_key: obj.image?.image_key || "",
            image_source_id: obj.image?.source?.id || null,
            image_file: null,
            image_file_sha512: obj.image?.sha512_hash || null,
        });
    };

    const handleEdit = (obj: any) => {
        setEditingId(obj.id);
        setForm({
            text_content: obj.text_content,
            image_path: obj.image_path,
            image_key: obj.image?.image_key || "",
            image_source_id: obj.image?.source?.id || null,
            image_file: null,
        });
    };

    const handleUpdate = async () => {
        const formData = new FormData();
        formData.append("text_content", form.text_content);
        formData.append("image_path", form.image_path);
        if (form.image_source_id)
            formData.append("image_source_id", form.image_source_id.toString());
        if (form.image_file)
            formData.append("image_file", form.image_file);

        await updateSearchObject(editingId!, formData);

        clearForm();
        fetchObjects(page, pageSize);
    };

    const handleDelete = async (id: number) => {
        if (confirm("Are you sure you want to delete this object?")) {
            await deleteSearchObject(id);
            fetchObjects(page, pageSize);
        }
    };

    const handleCreate = async () => {
        console.log("Creating object with form data:", form);
        if ((!form.image_file && !form.image_file_sha512) || form.image_source_id === null) {
            alert("Please select an image source and upload an image file.");
            return;
        }

        const formData = new FormData();
        formData.append("text_content", form.text_content);
        formData.append("image_path", form.image_path);
        formData.append("image_key", form.image_key);
        formData.append("image_source_id", form.image_source_id!.toString());
        if (form.image_file)
            formData.append("image_file", form.image_file);
        if (form.image_file_sha512)
            formData.append("image_file_sha512", form.image_file_sha512);

        await createSearchObject(formData);

        clearForm();
        fetchObjects(page, pageSize);
    };

    const pageCount = Math.ceil(total / pageSize);
    const visiblePages = getPaginationPages(page, pageCount);

    return (
        <div className="max-w-4xl mx-auto space-y-6">
            <h1 className="text-2xl">Admin Dashboard</h1>

            <div className="space-y-2">
                <Input placeholder="Text content" value={form.text_content}
                       onChange={(e) => setForm({...form, text_content: e.target.value})}/>
                <Input placeholder="Image path" value={form.image_path}
                       onChange={(e) => setForm({...form, image_path: e.target.value})}/>
                <Input placeholder="Image key" value={form.image_key}
                       onChange={(e) => setForm({...form, image_key: e.target.value})}/>

                {/* Dropdown for image sources */}
                <select
                    className="w-full p-2 border rounded"
                    value={form.image_source_id !== null ? form.image_source_id : ""}
                    onChange={(e) =>
                        setForm({
                            ...form,
                            image_source_id: e.target.value ? parseInt(e.target.value) : null,
                        })
                    }
                >
                    <option value="">Select Image Source</option>
                    {imageSources.map(src => (
                        <option key={src.id} value={src.id}>{src.source_name}</option>
                    ))}
                </select>

                <Input type="file" onChange={(e) => setForm({
                    ...form,
                    image_file: e.target.files?.[0] ?? null,
                    image_file_sha512: ""
                })}/>
                <Input value={form.image_file_sha512} hidden={true}
                       onChange={(e) => setForm({...form, image_file_sha512: e.target.value})}
                       placeholder="Image file SHA-512"/>
                <Button onClick={handleCreate}>Create Object</Button>
            </div>

            <Input
                className="w-full"
                placeholder="Search by content..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
            />

            {objects.map((obj: any) => (
                <Card key={obj.id} className="mb-4">
                    <CardContent className="p-4">
                        {editingId === obj.id ? (
                            <div className="space-y-2">
                                <Input value={form.text_content}
                                       onChange={(e) => setForm({...form, text_content: e.target.value})}/>
                                <Input value={form.image_path}
                                       onChange={(e) => setForm({...form, image_path: e.target.value})}/>
                                <Input value={form.image_key}
                                       onChange={(e) => setForm({...form, image_key: e.target.value})}/>
                                <select
                                    className="w-full p-2 border rounded"
                                    value={form.image_source_id !== null ? form.image_source_id : ""}
                                    onChange={(e) =>
                                        setForm({
                                            ...form,
                                            image_source_id: e.target.value ? parseInt(e.target.value) : null,
                                        })
                                    }
                                >
                                    <option value="">Select Image Source</option>
                                    {imageSources.map((src: any) => (
                                        <option key={src.id} value={src.id}>{src.source_name}</option>
                                    ))}
                                </select>
                                <Input type="file"
                                       onChange={(e) => setForm({
                                           ...form,
                                           image_file: e.target.files?.[0] ?? null,
                                           image_file_sha512: ""
                                       })}/>
                                <Button onClick={handleUpdate}>Save Changes</Button>
                                <Button variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                            </div>
                        ) : (
                            <>
                                <div className="font-bold">
                                    <Highlighter
                                        searchWords={[query]}
                                        autoEscape
                                        textToHighlight={obj.text_content}
                                    />
                                </div>
                                <div className="text-sm text-muted-foreground">
                                    <Highlighter
                                        searchWords={[query]}
                                        autoEscape
                                        textToHighlight={`${obj.image?.image_path} (${obj.image?.source?.source_name}) ${obj.image?.image_key}`}
                                    />
                                </div>
                                <img
                                    src={`http://localhost:8000${obj.thumbnail_url}`}
                                    alt="result"
                                    className="w-20 h-20 object-cover rounded cursor-pointer"
                                    onClick={() => setPopupImage(obj.image_url)}
                                />
                                <Button size="sm" className="mr-2 mt-2" onClick={() => handleEdit(obj)}>Edit</Button>
                                <Button size="sm" className="mr-2 mt-2" onClick={() => handleClone(obj)}>Clone</Button>
                                <Button variant="destructive" size="sm"
                                        onClick={() => handleDelete(obj.id)}>Delete</Button>
                            </>
                        )}
                    </CardContent>
                </Card>
            ))}
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
            {popupImage && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
                    onClick={() => {
                        setPopupImage(null);
                        setIsZoomed(false);
                    }}
                >
                    <div
                        className={`max-w-full max-h-full overflow-${isZoomed ? 'auto' : 'hidden'}`}
                        onClick={(e) => e.stopPropagation()} // prevent close on image click
                    >
                        <img
                            src={`http://localhost:8000${popupImage}`}
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
