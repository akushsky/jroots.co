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
import {paths} from "@/types/api";
import {Tooltip, TooltipContent, TooltipProvider, TooltipTrigger} from "@/components/ui/tooltip.tsx";

interface ImageSource {
    id: number;
    source_name: string;
}

interface FormState {
    text_content: string;
    price: number | null;
    image_path: string;
    image_key: string;
    image_source_id: number | null;
    image_file: File | null;
    image_file_sha512?: string;
}

type SearchResponse = paths["/api/search"]["get"]["responses"]["200"];
type SearchResponseBody = SearchResponse["content"]["application/json"];
type SearchObject = SearchResponseBody["items"][number];

export default function AdminDashboard() {
    const [objects, setObjects] = useState<SearchObject[]>([]);
    const [query, setQuery] = useState("");
    const [imageSources, setImageSources] = useState<ImageSource[]>([]);
    const [popupImage, setPopupImage] = useState<string | null>(null);
    const [isZoomed, setIsZoomed] = useState(false);

    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const pageSize = 20;

    const [dragOver, setDragOver] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState<FormState>({
        text_content: "",
        price: 0,
        image_path: "",
        image_key: "",
        image_source_id: null,
        image_file: null,
        image_file_sha512: "",
    });

    const fetchSources = () => apiClient.get("/admin/image-sources").then(res => setImageSources(res.data));

    const fetchPage = async () => {
        if (query.trim()) {
            setPage(0);
            const res = await searchObjects(query, page, pageSize);
            setObjects([...res.items]);
            setTotal(res.total);
        } else {
            const res = await fetchObjects(page, pageSize);
            setObjects([...res.items]);
            setTotal(res.total);
        }
    }

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
            await fetchPage()
        }, 300);

        return () => clearTimeout(delay);
    }, [query, page]);

    const clearForm = () => {
        setForm({
            text_content: "",
            price: 0,
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
            price: obj.price,
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
            price: obj.price,
            image_path: obj.image?.image_path,
            image_key: obj.image?.image_key || "",
            image_source_id: obj.image?.source?.id || null,
            image_file_sha512: obj.image?.sha512_hash || null,
            image_file: null,
        });
    };

    const handleUpdate = async () => {
        const formData = new FormData();
        formData.append("text_content", form.text_content);
        formData.append("price", form.price?.toString() || "");
        formData.append("image_path", form.image_path);
        formData.append("image_key", form.image_key);
        if (form.image_source_id)
            formData.append("image_source_id", form.image_source_id.toString());
        if (form.image_file)
            formData.append("image_file", form.image_file);

        await updateSearchObject(editingId!, formData);

        clearForm();

        await fetchPage();
    };

    const handleDelete = async (id: number) => {
        if (confirm("Вы точно хотите забыть об этом навсегда?")) {
            await deleteSearchObject(id);
            await fetchPage();
        }
    };

    const handleCreate = async () => {
        console.log("Creating object with form data:", form);
        if ((!form.image_file && !form.image_file_sha512) || form.image_source_id === null) {
            alert("Источник информации и скан-копия - обязательные для заполнения поля.");
            return;
        }

        const formData = new FormData();
        formData.append("text_content", form.text_content);
        formData.append("price", form.price?.toString() || "");
        formData.append("image_path", form.image_path);
        formData.append("image_key", form.image_key);
        formData.append("image_source_id", form.image_source_id!.toString());
        if (form.image_file)
            formData.append("image_file", form.image_file);
        if (form.image_file_sha512)
            formData.append("image_file_sha512", form.image_file_sha512);

        await createSearchObject(formData);

        clearForm();

        await fetchPage();
    };

    const pageCount = Math.ceil(total / pageSize);
    const visiblePages = getPaginationPages(page, pageCount);

    return (
        <div className="max-w-4xl mx-auto space-y-6">
            <h1 className="text-2xl">Никто не забыт</h1>

            <div className="space-y-2">
                <Input placeholder="ФИО" value={form.text_content}
                       onChange={(e) => setForm({...form, text_content: e.target.value})}/>
                <Input placeholder="Стоимость" value={form.price?.toString()}
                       onChange={(e) => setForm({...form, price: parseInt(e.target.value)})}/>
                <Input placeholder="Шифр" value={form.image_path}
                       onChange={(e) => setForm({...form, image_path: e.target.value})}/>
                <Input placeholder="Описание" value={form.image_key}
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
                    <option value="">Источник информации</option>
                    {imageSources.map(src => (
                        <option key={src.id} value={src.id}>{src.source_name}</option>
                    ))}
                </select>

                <div
                    className={`w-full border-2 border-dashed rounded-xl p-4 text-center transition-all duration-200 cursor-pointer
                                ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300'}
                               `}
                    onDragOver={(e) => {
                        e.preventDefault();
                        setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => {
                        e.preventDefault();
                        setDragOver(false);
                        const file = e.dataTransfer.files?.[0];
                        if (file) setForm({
                            ...form,
                            image_file: file ?? null,
                            image_file_sha512: ""
                        });
                    }}
                    onClick={() => document.getElementById('fileInput')?.click()}
                >
                    {form.image_file ? (
                        <div className="text-sm text-gray-800">
                            <img
                                src={URL.createObjectURL(form.image_file)}
                                alt="Preview"
                                className="mt-2 max-h-48 mx-auto rounded shadow"
                            />
                            {form.image_file.name}
                        </div>
                    ) : (
                        <div className="text-gray-500">Перетащите изображение сюда или нажмите, чтобы выбрать файл</div>
                    )}
                </div>

                <Input
                    id="fileInput"
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) setForm({
                            ...form,
                            image_file: file ?? null,
                            image_file_sha512: ""
                        })
                    }}
                />

                <Input value={form.image_file_sha512} hidden={true}
                       onChange={(e) => setForm({...form, image_file_sha512: e.target.value})}
                       placeholder="Image file SHA-512"/>
                <Button onClick={handleCreate}>Запомнить</Button>
            </div>

            <Input
                className="w-full"
                placeholder="Поиск..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
            />

            {objects.map((obj: any) => (
                <Card key={obj.id} className="mb-4">
                    <div className="relative">
                        <CardContent className="p-4">
                            {editingId === obj.id ? (
                                <div className="space-y-2">
                                    <Input value={form.text_content}
                                           onChange={(e) => setForm({...form, text_content: e.target.value})}/>
                                    <Input value={form.price?.toString()}
                                           onChange={(e) => setForm({...form, price: parseInt(e.target.value)})}/>
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
                                        <option value="">Источник информации</option>
                                        {imageSources.map((src: any) => (
                                            <option key={src.id} value={src.id}>{src.source_name}</option>
                                        ))}
                                    </select>

                                    <div
                                        className={`w-full border-2 border-dashed rounded-xl p-4 text-center transition-all duration-200 cursor-pointer
                                ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300'}
                               `}
                                        onDragOver={(e) => {
                                            e.preventDefault();
                                            setDragOver(true);
                                        }}
                                        onDragLeave={() => setDragOver(false)}
                                        onDrop={(e) => {
                                            e.preventDefault();
                                            setDragOver(false);
                                            const file = e.dataTransfer.files?.[0];
                                            if (file) setForm({
                                                ...form,
                                                image_file: file ?? null,
                                                image_file_sha512: ""
                                            });
                                        }}
                                        onClick={() => document.getElementById('fileInput')?.click()}
                                    >
                                        {form.image_file ? (
                                            <div className="text-sm text-gray-800">
                                                <img
                                                    src={URL.createObjectURL(form.image_file)}
                                                    alt="Preview"
                                                    className="mt-2 max-h-48 mx-auto rounded shadow"
                                                />
                                                {form.image_file.name}
                                            </div>
                                        ) : (
                                            <div className="text-gray-500">Перетащите изображение сюда или нажмите,
                                                чтобы выбрать файл</div>
                                        )}
                                    </div>

                                    <Input
                                        id="fileInput"
                                        type="file"
                                        accept="image/*"
                                        className="hidden"
                                        onChange={(e) => {
                                            const file = e.target.files?.[0];
                                            if (file) setForm({
                                                ...form,
                                                image_file: file ?? null,
                                                image_file_sha512: ""
                                            })
                                        }}
                                    />

                                    <Button onClick={handleUpdate}>Запомнить</Button>
                                    <Button variant="ghost" onClick={() => setEditingId(null)}>Не менять</Button>
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
                                        src={`${obj.thumbnail_url}`}
                                        alt="result"
                                        className="w-20 h-20 object-cover rounded cursor-pointer"
                                        onClick={() => setPopupImage(obj.image_url)}
                                    />
                                    <Button size="sm" className="mr-2 mt-2"
                                            onClick={() => handleEdit(obj)}>Редактировать</Button>
                                    <Button size="sm" className="mr-2 mt-2"
                                            onClick={() => handleClone(obj)}>Дублировать</Button>
                                    <Button variant="destructive" size="sm"
                                            onClick={() => handleDelete(obj.id)}>Забыть навсегда</Button>
                                </>
                            )}
                        </CardContent>
                        {obj.price !== undefined && (
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <div
                                            className="absolute top-2 right-2 bg-blue-600 text-white text-xs px-3 py-1 rounded-full shadow cursor-help">
                                            {(obj.price / 100).toFixed(2)} €
                                        </div>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p>Цена за просмотр полного изображения и метаданных</p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                        )}
                    </div>
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
                    {/* Close button */}
                    <button
                        className="absolute top-4 right-4 text-white text-3xl font-bold z-50 bg-black/50 rounded-full w-10 h-10 flex items-center justify-center"
                        onClick={(e) => {
                            e.stopPropagation(); // prevent outer click handler
                            setPopupImage(null);
                            setIsZoomed(false);
                        }}
                        aria-label="Закрыть изображение"
                    >
                        ×
                    </button>
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
