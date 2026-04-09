interface StatusMessageProps {
    type: "success" | "error";
    message: string;
}

export function StatusMessage({type, message}: StatusMessageProps) {
    const styles =
        type === "success"
            ? "bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-300"
            : "bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-300";

    return (
        <div className={`${styles} px-4 py-2 rounded text-sm`} role="alert">
            {message}
        </div>
    );
}
