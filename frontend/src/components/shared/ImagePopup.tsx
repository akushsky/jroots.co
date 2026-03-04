import {useEffect, useState} from "react";

interface ImagePopupProps {
    imageUrl: string | null;
    onClose: () => void;
}

export function ImagePopup({imageUrl, onClose}: ImagePopupProps) {
    const [isZoomed, setIsZoomed] = useState(false);

    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                onClose();
            }
        };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [onClose]);

    if (!imageUrl) return null;

    return (
        <div
            className="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
            onClick={() => {
                onClose();
                setIsZoomed(false);
            }}
        >
            <button
                className="absolute top-4 right-4 text-white text-3xl font-bold z-50 bg-black/50 rounded-full w-10 h-10 flex items-center justify-center"
                onClick={(e) => {
                    e.stopPropagation();
                    onClose();
                    setIsZoomed(false);
                }}
                aria-label="Закрыть изображение"
            >
                &times;
            </button>
            <div
                className={`max-w-full max-h-full ${isZoomed ? "overflow-auto" : "overflow-hidden"}`}
                onClick={(e) => e.stopPropagation()}
            >
                <img
                    src={imageUrl}
                    alt="Полный размер"
                    className={`transition-all duration-300 shadow-2xl rounded ${
                        isZoomed ? "cursor-zoom-out" : "cursor-zoom-in"
                    }`}
                    style={{
                        width: isZoomed ? "auto" : "100%",
                        height: "auto",
                        maxWidth: isZoomed ? "none" : "100vw",
                        maxHeight: isZoomed ? "none" : "100vh",
                        display: "block",
                    }}
                    onClick={() => setIsZoomed((z) => !z)}
                />
            </div>
        </div>
    );
}
