import {useState} from "react";
import {SendHorizonal} from "lucide-react";
import {Button} from "@/components/ui/button";

interface ChatInputProps {
    disabled: boolean;
    onSend: (content: string) => void;
}

export function ChatInput({disabled, onSend}: ChatInputProps) {
    const [value, setValue] = useState("");

    const submit = () => {
        const content = value.trim();
        if (!content || disabled) return;
        onSend(content);
        setValue("");
    };

    return (
        <div className="flex items-end gap-2">
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
                disabled={disabled || !value.trim()}
                size="icon"
                aria-label="Отправить"
            >
                <SendHorizonal />
            </Button>
        </div>
    );
}
