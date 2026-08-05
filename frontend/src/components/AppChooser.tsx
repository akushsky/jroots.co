import {Link} from "react-router-dom";
import {MessagesSquare, Search} from "lucide-react";
import {Card, CardContent} from "@/components/ui/card";

const TOOLS = [
    {
        to: "/chat",
        icon: MessagesSquare,
        title: "Чат-ассистент",
        description:
            "Расскажите, кого ищете — ассистент сам пройдёт по архивам, покажет записи и сканы. Подходит, даже если вы никогда не работали с фондами.",
        cta: "Перейти в чат",
        testId: "tool-chat",
    },
    {
        to: "/",
        icon: Search,
        title: "Профессиональный поиск",
        description:
            "Проект «Внезапные евреи»: прямой поиск по агрегированной базе фондов и сканов. Для тех, кто предпочитает копать сам.",
        cta: "Открыть поиск",
        testId: "tool-search",
    },
];

export default function AppChooser() {
    return (
        <div className="max-w-3xl mx-auto px-4 pt-10 space-y-8">
            <div className="text-center space-y-2">
                <h1 className="font-display text-3xl md:text-4xl font-bold">С чего начнём?</h1>
                <p className="text-muted-foreground">
                    JRoots — два инструмента для поиска документов вашей семьи.
                </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
                {TOOLS.map((tool) => (
                    <Link key={tool.to} to={tool.to} data-testid={tool.testId} className="group">
                        <Card className="h-full transition-colors group-hover:border-accent">
                            <CardContent className="p-6 flex flex-col gap-3 h-full">
                                <tool.icon className="w-7 h-7 text-accent" />
                                <h2 className="font-display text-xl font-semibold">{tool.title}</h2>
                                <p className="text-sm text-muted-foreground flex-1">
                                    {tool.description}
                                </p>
                                <span className="text-sm font-medium text-accent group-hover:underline">
                                    {tool.cta} →
                                </span>
                            </CardContent>
                        </Card>
                    </Link>
                ))}
            </div>
        </div>
    );
}
