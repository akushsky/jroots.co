import {Package, RefreshCw} from "lucide-react";
import {Card, CardContent} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Tooltip, TooltipContent, TooltipTrigger} from "@/components/ui/tooltip";

const COMING_SOON = "Скоро — оплата появится в одном из ближайших обновлений";

interface Tariff {
    name: string;
    price: string;
    description: string;
    icon: typeof Package;
}

const TARIFFS: Tariff[] = [
    {
        name: "Пакет «Дело»",
        price: "$25",
        description: "25 поисков и 10 сканов документов — хватит на одно семейное дело от начала до архивного запроса.",
        icon: Package,
    },
    {
        name: "Подписка «Исследователь»",
        price: "$15/мес",
        description: "Постоянный доступ к ассистенту для тех, кто ведёт несколько ветвей семьи параллельно.",
        icon: RefreshCw,
    },
];

function DisabledAction({label, small}: { label: string; small?: boolean }) {
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                {/* span needed: tooltips don't attach to disabled buttons */}
                <span className="inline-block">
                    <Button disabled size={small ? "sm" : "default"} variant={small ? "link" : "default"}>
                        {label}
                    </Button>
                </span>
            </TooltipTrigger>
            <TooltipContent>{COMING_SOON}</TooltipContent>
        </Tooltip>
    );
}

export function Paywall() {
    return (
        <div className="space-y-4" data-testid="paywall">
            <div className="text-center">
                <h3 className="font-display text-xl font-semibold">Бесплатные поиски закончились</h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Выберите тариф, чтобы продолжить исследование семейной истории.
                </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
                {TARIFFS.map((tariff) => (
                    <Card key={tariff.name}>
                        <CardContent className="p-4 space-y-3">
                            <div className="flex items-center gap-2">
                                <tariff.icon className="w-4 h-4 text-accent" />
                                <span className="font-semibold">{tariff.name}</span>
                                <span className="ml-auto font-display text-lg">{tariff.price}</span>
                            </div>
                            <p className="text-sm text-muted-foreground">{tariff.description}</p>
                            <DisabledAction label="Оформить" />
                        </CardContent>
                    </Card>
                ))}
            </div>
            <div className="text-center">
                <DisabledAction label="Или разблокировать одну запись" small />
            </div>
        </div>
    );
}
