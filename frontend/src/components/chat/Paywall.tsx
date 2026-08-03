import {useState} from "react";
import axios from "axios";
import {Loader2, Package, RefreshCw} from "lucide-react";
import {Card, CardContent} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Tooltip, TooltipContent, TooltipTrigger} from "@/components/ui/tooltip";
import {cn} from "@/lib/utils";
import {createCheckout} from "@/api/payments";
import type {PaymentProvider, PaymentTariff} from "@/api/payments";

const SUBSCRIPTION_TOOLTIP = "Подписка — только картой";
const CHECKOUT_FAILED = "Не удалось открыть страницу оплаты. Попробуйте ещё раз.";

const PROVIDERS: Array<{ id: PaymentProvider; label: string }> = [
    {id: "polar", label: "Карта"},
    {id: "nowpayments", label: "Крипта"},
    {id: "yukassa", label: "₽"},
];

interface Tariff {
    code: PaymentTariff;
    name: string;
    price: string;
    description: string;
    icon: typeof Package;
    /** Subscriptions run on recurring billing, which only the Polar rail supports. */
    subscription?: boolean;
}

const TARIFFS: Tariff[] = [
    {
        code: "delo",
        name: "Пакет «Дело»",
        price: "$25",
        description: "25 поисков и 10 сканов документов — хватит на одно семейное дело от начала до архивного запроса.",
        icon: Package,
    },
    {
        code: "researcher",
        name: "Подписка «Исследователь»",
        price: "$15/мес",
        description: "Постоянный доступ к ассистенту для тех, кто ведёт несколько ветвей семьи параллельно.",
        icon: RefreshCw,
        subscription: true,
    },
];

interface ProviderSwitchProps {
    value: PaymentProvider;
    onChange: (provider: PaymentProvider) => void;
    lockToPolar?: boolean;
}

function ProviderSwitch({value, onChange, lockToPolar}: ProviderSwitchProps) {
    return (
        <div
            className="inline-flex items-center gap-0.5 rounded-md border border-border p-0.5"
            role="radiogroup"
            aria-label="Способ оплаты"
        >
            {PROVIDERS.map((provider) => {
                const locked = lockToPolar && provider.id !== "polar";
                const button = (
                    <button
                        key={provider.id}
                        type="button"
                        role="radio"
                        aria-checked={value === provider.id}
                        disabled={locked}
                        onClick={() => onChange(provider.id)}
                        className={cn(
                            "px-2 py-1 text-xs rounded transition-colors",
                            value === provider.id
                                ? "bg-accent text-accent-foreground"
                                : "text-muted-foreground hover:text-foreground",
                            locked && "opacity-50 cursor-not-allowed",
                        )}
                    >
                        {provider.label}
                    </button>
                );
                if (!locked) return button;
                return (
                    <Tooltip key={provider.id}>
                        <TooltipTrigger asChild>
                            {/* span needed: tooltips don't attach to disabled buttons */}
                            <span className="inline-block">{button}</span>
                        </TooltipTrigger>
                        <TooltipContent>{SUBSCRIPTION_TOOLTIP}</TooltipContent>
                    </Tooltip>
                );
            })}
        </div>
    );
}

interface CheckoutError {
    tariff: PaymentTariff;
    message: string;
}

interface PaywallProps {
    title?: string;
    description?: string;
}

export function Paywall({
    title = "Бесплатные поиски закончились",
    description = "Выберите тариф, чтобы продолжить исследование семейной истории.",
}: PaywallProps) {
    const [providers, setProviders] = useState<Partial<Record<PaymentTariff, PaymentProvider>>>({});
    const [loadingTariff, setLoadingTariff] = useState<PaymentTariff | null>(null);
    const [checkoutError, setCheckoutError] = useState<CheckoutError | null>(null);

    const providerFor = (tariff: Tariff): PaymentProvider =>
        tariff.subscription ? "polar" : (providers[tariff.code] ?? "polar");

    const startCheckout = async (tariff: PaymentTariff, provider: PaymentProvider) => {
        setLoadingTariff(tariff);
        setCheckoutError(null);
        try {
            const {checkout_url} = await createCheckout(tariff, provider);
            window.location.assign(checkout_url);
        } catch (error) {
            const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null;
            setCheckoutError({
                tariff,
                message: typeof detail === "string" ? detail : CHECKOUT_FAILED,
            });
        } finally {
            setLoadingTariff(null);
        }
    };

    const renderCheckoutButton = (tariff: PaymentTariff, provider: PaymentProvider, label: string) => {
        const loading = loadingTariff === tariff;
        return (
            <Button
                size="sm"
                disabled={loadingTariff !== null}
                onClick={() => startCheckout(tariff, provider)}
            >
                {loading && <Loader2 className="animate-spin" />}
                {loading ? "Переход к оплате…" : label}
            </Button>
        );
    };

    const pprProvider = providers.ppr ?? "polar";

    return (
        <div className="space-y-4" data-testid="paywall">
            <div className="text-center">
                <h3 className="font-display text-xl font-semibold">{title}</h3>
                <p className="text-sm text-muted-foreground mt-1">
                    {description}
                </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
                {TARIFFS.map((tariff) => (
                    <Card key={tariff.code} data-testid={`tariff-${tariff.code}`}>
                        <CardContent className="p-4 space-y-3">
                            <div className="flex items-center gap-2">
                                <tariff.icon className="w-4 h-4 text-accent" />
                                <span className="font-semibold">{tariff.name}</span>
                                <span className="ml-auto font-display text-lg">{tariff.price}</span>
                            </div>
                            <p className="text-sm text-muted-foreground">{tariff.description}</p>
                            <div className="flex items-center justify-between gap-2">
                                <ProviderSwitch
                                    value={providerFor(tariff)}
                                    onChange={(provider) =>
                                        setProviders((prev) => ({...prev, [tariff.code]: provider}))
                                    }
                                    lockToPolar={tariff.subscription}
                                />
                                {renderCheckoutButton(tariff.code, providerFor(tariff), "Оформить")}
                            </div>
                            {checkoutError?.tariff === tariff.code && (
                                <p role="alert" className="text-xs text-destructive">
                                    {checkoutError.message}
                                </p>
                            )}
                        </CardContent>
                    </Card>
                ))}
            </div>
            <div className="flex flex-col items-center gap-2" data-testid="tariff-ppr">
                <div className="flex items-center justify-center gap-2">
                    <ProviderSwitch
                        value={pprProvider}
                        onChange={(provider) => setProviders((prev) => ({...prev, ppr: provider}))}
                    />
                    {renderCheckoutButton("ppr", pprProvider, "Разблокировать одну запись — $3")}
                </div>
                {checkoutError?.tariff === "ppr" && (
                    <p role="alert" className="text-xs text-destructive">
                        {checkoutError.message}
                    </p>
                )}
            </div>
        </div>
    );
}
