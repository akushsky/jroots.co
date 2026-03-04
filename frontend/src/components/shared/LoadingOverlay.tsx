interface LoadingOverlayProps {
    message?: string;
}

export function LoadingOverlay({message = "Загрузка..."}: LoadingOverlayProps) {
    return (
        <div
            className="fixed inset-0 bg-black/70 flex flex-col items-center justify-center z-50"
            role="status"
            aria-live="polite"
        >
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-white border-t-transparent mb-4" />
            <p className="text-white text-lg">{message}</p>
        </div>
    );
}
