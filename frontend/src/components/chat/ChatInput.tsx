import {useRef, useState} from "react";
import {AlertTriangle, Check, Loader2, Paperclip, SendHorizonal, X} from "lucide-react";
import {Button} from "@/components/ui/button";
import {Tooltip, TooltipContent, TooltipTrigger} from "@/components/ui/tooltip";
import {cn} from "@/lib/utils";
import {SCAN_ACCEPT, validateScanFile, type ScanAttachment} from "./scans";
import {useOpenPaywall} from "./PaywallContext";

interface ChatInputProps {
    disabled: boolean;
    attachments: ScanAttachment[];
    onAttachFile: (file: File) => void;
    onRemoveAttachment: (localId: string) => void;
    onSend: (content: string) => void;
    /** Prefill the input (e.g. from /chat?q=... landing hand-off). Applied on mount. */
    initialValue?: string;
}

function AttachmentChip({attachment, onRemove}: { attachment: ScanAttachment; onRemove: () => void }) {
    const openPaywall = useOpenPaywall();

    if (attachment.errorCode === "no_scans_left") {
        return (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-1">
                <button
                    type="button"
                    onClick={openPaywall}
                    className="inline-flex items-center gap-1 text-xs text-amber-700 hover:underline"
                >
                    <AlertTriangle className="w-3 h-3" />
                    Сканы закончились
                </button>
                <button
                    type="button"
                    onClick={onRemove}
                    aria-label="Скрыть уведомление о сканах"
                    className="text-muted-foreground hover:text-foreground"
                >
                    <X className="w-3 h-3" />
                </button>
            </span>
        );
    }

    return (
        <span
            className={cn(
                "inline-flex items-center gap-2 rounded-lg border px-2 py-1",
                attachment.status === "error"
                    ? "border-destructive/40 bg-destructive/10"
                    : "border-border bg-muted",
            )}
        >
            <img src={attachment.previewUrl} alt="" className="w-8 h-8 rounded object-cover" />
            <span className="flex flex-col min-w-0 max-w-[160px]">
                <span className="text-xs truncate">{attachment.fileName}</span>
                {attachment.status === "uploading" && (
                    <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Обработка…
                    </span>
                )}
                {attachment.status === "done" && (
                    <span className="inline-flex items-center gap-1 text-[10px] text-green-600">
                        <Check className="w-3 h-3" />
                        Готово
                    </span>
                )}
                {attachment.status === "done" && attachment.confidence === "low" && (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <span className="inline-flex items-center self-start text-[10px] text-amber-700 bg-amber-500/10 border border-amber-500/40 rounded-full px-1.5 py-0.5 cursor-help">
                                неуверенное чтение
                            </span>
                        </TooltipTrigger>
                        <TooltipContent>документ прочитан частично, проверьте транскрипцию</TooltipContent>
                    </Tooltip>
                )}
                {attachment.status === "error" && attachment.errorText && (
                    <span className="text-[10px] text-destructive leading-tight">{attachment.errorText}</span>
                )}
            </span>
            <button
                type="button"
                onClick={onRemove}
                aria-label={`Удалить скан ${attachment.fileName}`}
                className="self-start text-muted-foreground hover:text-foreground"
            >
                <X className="w-3.5 h-3.5" />
            </button>
        </span>
    );
}

export function ChatInput({disabled, attachments, onAttachFile, onRemoveAttachment, onSend, initialValue}: ChatInputProps) {
    const [value, setValue] = useState(initialValue ?? "");
    const [attachError, setAttachError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const uploading = attachments.some((a) => a.status === "uploading");

    const submit = () => {
        const content = value.trim();
        if (!content || disabled || uploading) return;
        onSend(content);
        setValue("");
    };

    const pickFiles = (files: FileList | null) => {
        if (!files) return;
        setAttachError(null);
        for (const file of Array.from(files)) {
            const error = validateScanFile(file);
            if (error) {
                setAttachError(`${file.name}: ${error}`);
                continue;
            }
            onAttachFile(file);
        }
    };

    return (
        <div className="flex flex-col gap-2">
            {attachments.length > 0 && (
                <div className="flex flex-wrap gap-2">
                    {attachments.map((attachment) => (
                        <AttachmentChip
                            key={attachment.localId}
                            attachment={attachment}
                            onRemove={() => onRemoveAttachment(attachment.localId)}
                        />
                    ))}
                </div>
            )}
            {attachError && <p className="text-xs text-destructive">{attachError}</p>}
            <div className="flex items-end gap-2">
                <input
                    ref={fileInputRef}
                    type="file"
                    accept={SCAN_ACCEPT}
                    multiple
                    className="hidden"
                    aria-label="Файл скана"
                    onChange={(e) => {
                        pickFiles(e.target.files);
                        // allow picking the same file again
                        e.target.value = "";
                    }}
                />
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={disabled}
                    aria-label="Прикрепить скан"
                >
                    <Paperclip />
                </Button>
                <textarea
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            submit();
                        }
                    }}
                    disabled={disabled}
                    rows={2}
                    placeholder="Опишите, кого ищете: фамилия, имя, место, примерные годы…"
                    aria-label="Сообщение ассистенту"
                    className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:opacity-50"
                />
                <Button
                    onClick={submit}
                    disabled={disabled || !value.trim() || uploading}
                    size="icon"
                    aria-label="Отправить"
                >
                    <SendHorizonal />
                </Button>
            </div>
        </div>
    );
}
