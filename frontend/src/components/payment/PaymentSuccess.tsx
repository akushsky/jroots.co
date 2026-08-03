import {useEffect, useState} from "react";
import {Link} from "react-router-dom";
import {CheckCircle2, Loader2} from "lucide-react";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {getCredits} from "@/api/chat";
import type {Credits} from "@/api/chat";

const POLL_INTERVAL_MS = 2500;
/** 6 polls at 2.5s ≈ 15s of waiting for the webhook to grant credits. */
const MAX_POLLS = 6;

/**
 * Return page after a successful checkout. Credits are granted by the
 * provider webhook asynchronously, so the balance is polled for up to
 * 15 seconds while the webhook catches up.
 */
export default function PaymentSuccess() {
    const [credits, setCredits] = useState<Credits | null>(null);
    const [polling, setPolling] = useState(true);

    useEffect(() => {
        let cancelled = false;
        let timer: ReturnType<typeof setTimeout> | undefined;
        let attempts = 0;

        const poll = async () => {
            attempts += 1;
            try {
                const balance = await getCredits();
                if (!cancelled) setCredits(balance);
            } catch {
                // Balance read failed (e.g. expired token) — keep polling until timeout.
            }
            if (cancelled) return;
            if (attempts < MAX_POLLS) {
                timer = setTimeout(poll, POLL_INTERVAL_MS);
            } else {
                setPolling(false);
            }
        };

        void poll();
        return () => {
            cancelled = true;
            if (timer !== undefined) clearTimeout(timer);
        };
    }, []);

    return (
        <div className="flex justify-center px-4" data-testid="payment-success">
            <Card className="max-w-md w-full">
                <CardContent className="p-6 space-y-4 text-center">
                    <CheckCircle2 className="w-10 h-10 mx-auto text-accent" />
                    <h1 className="font-display text-2xl font-semibold">Оплата прошла</h1>
                    <p className="text-sm text-muted-foreground">
                        Кредиты начисляются — обычно это занимает несколько секунд.
                    </p>
                    {credits !== null && (
                        <p className="text-sm bg-secondary rounded-full px-4 py-2 inline-block">
                            Осталось поисков: {credits.searches_left} · Сканов: {credits.scans_left}
                        </p>
                    )}
                    {polling && (
                        <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Обновляем баланс…
                        </p>
                    )}
                    <div>
                        <Button asChild>
                            <Link to="/chat">В чат</Link>
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
