import {useState} from "react";
import {Link, useNavigate} from "react-router-dom";
import {ArrowRight, BookOpen, FileSearch, ScrollText} from "lucide-react";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {Paywall} from "@/components/chat/Paywall";

const STEPS = [
    {
        icon: FileSearch,
        title: "Расскажите, кого ищете",
        text: "Фамилия, имя, место, примерные годы — даже отрывочные сведения подойдут. Ассистент уточнит недостающее.",
    },
    {
        icon: ScrollText,
        title: "Ассистент ищет по архивам",
        text: "Метрические книги, ревизские сказки, списки захоронений и эвакуации — десятки баз и фондов в одном диалоге.",
    },
    {
        icon: BookOpen,
        title: "Получите документы",
        text: "Записи, сканы и ссылки на источники — то, что консульство принимает как доказательство корней.",
    },
];

const EXAMPLES = [
    {
        label: "Метрические книги",
        question: "Бабушка Роза Гольдберг, родилась около 1890 года в Кишинёве. С чего начать?",
        answer: "Начните с метрических книг кишинёвской синагоги: записи о рождении за 1890–1893 годы хранятся в Национальном архиве Молдовы. Параллельно проверьте ревизские сказки Кишинёва за 1850 и 1858 годы по семье Гольдберг. Запись о рождении даст имена родителей — это ещё одно поколение вверх по древу.",
    },
    {
        label: "Захоронения",
        question: "Дед Абрам Лейбович пропал без вести в 1943 году под Воронежем. Где искать могилу?",
        answer: "Проверьте базы «ОБД Мемориал» и «Память народа» по фамилии и году рождения. Если он есть в донесении о безвозвратных потерях, там указана первичная могила. Затем — списки захоронений Воронежской области и запрос в военкомат по месту призыва: послужная картотека часто хранит адрес семьи.",
    },
];

const ARTICLES = [
    {
        title: "Как доказать еврейские корни",
        lead: "Какая доказательная цепочка нужна консульству и почему одна метрика решает больше, чем семейные предания.",
    },
    {
        title: "Документы для репатриации из архивов",
        lead: "Метрики, домовые книги, ревизские сказки: какие записи принимают, а какие придётся подкреплять.",
    },
    {
        title: "Метрические книги: что это и где искать",
        lead: "Где хранятся книги синагог по губерниям, как читать записи и что делать, если книга не сохранилась.",
    },
];

export default function LandingPage() {
    const navigate = useNavigate();
    const [query, setQuery] = useState("");

    const submit = (e: React.FormEvent) => {
        e.preventDefault();
        const text = query.trim();
        if (!text) return;
        navigate(`/chat?q=${encodeURIComponent(text)}`);
    };

    return (
        <div className="max-w-5xl mx-auto px-4 space-y-16 pb-16">
            {/* Hero */}
            <section className="text-center pt-10 space-y-6">
                <h1 className="font-display text-4xl md:text-5xl font-bold leading-tight">
                    Найдите документы вашей семьи для репатриации
                </h1>
                <p className="text-muted-foreground max-w-2xl mx-auto">
                    Ассистент ищет метрики, ревизские сказки, списки захоронений и эвакуации
                    по десяткам архивов — и показывает записи, которые принимает консульство.
                </p>
                <form onSubmit={submit} className="flex gap-2 max-w-xl mx-auto">
                    <Input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Например: Рабиновичи из Бердичева, конец XIX века"
                        aria-label="Кого ищете"
                        className="h-11"
                    />
                    <Button type="submit" size="lg" disabled={!query.trim()}>
                        Начать поиск
                        <ArrowRight />
                    </Button>
                </form>
                <p className="text-xs text-muted-foreground">
                    Первые поиски — бесплатно, без карты.
                </p>
            </section>

            {/* How it works */}
            <section className="space-y-6">
                <h2 className="font-display text-3xl font-semibold text-center">Как это работает</h2>
                <div className="grid gap-4 md:grid-cols-3">
                    {STEPS.map((step, index) => (
                        <Card key={step.title}>
                            <CardContent className="p-5 space-y-3">
                                <div className="flex items-center gap-3">
                                    <span className="font-display text-2xl text-accent">{index + 1}</span>
                                    <step.icon className="w-5 h-5 text-accent" />
                                </div>
                                <h3 className="font-semibold">{step.title}</h3>
                                <p className="text-sm text-muted-foreground">{step.text}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </section>

            {/* Example dialogs */}
            <section className="space-y-6">
                <h2 className="font-display text-3xl font-semibold text-center">Так выглядит поиск</h2>
                <div className="grid gap-4 md:grid-cols-2">
                    {EXAMPLES.map((example) => (
                        <Card key={example.label}>
                            <CardContent className="p-5 space-y-3">
                                <span className="text-xs uppercase tracking-wide text-muted-foreground">
                                    {example.label}
                                </span>
                                <div className="flex justify-end">
                                    <div className="max-w-[90%] rounded-2xl rounded-br-md bg-accent text-accent-foreground px-3.5 py-2 text-sm shadow-xs">
                                        {example.question}
                                    </div>
                                </div>
                                <div className="flex justify-start">
                                    <div className="max-w-[90%] rounded-2xl rounded-bl-md bg-secondary text-secondary-foreground px-3.5 py-2 text-sm shadow-xs">
                                        {example.answer}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </section>

            {/* Tariffs */}
            <section className="space-y-6">
                <Paywall
                    title="Тарифы"
                    description="Начните бесплатно, продолжите — когда увидите первые записи своей семьи."
                />
            </section>

            {/* SEO articles */}
            <section className="space-y-6">
                <h2 className="font-display text-3xl font-semibold text-center">Полезные материалы</h2>
                <div className="grid gap-4 md:grid-cols-3">
                    {ARTICLES.map((article) => (
                        <Card key={article.title}>
                            <CardContent className="p-5 space-y-2">
                                <h3 className="font-semibold">
                                    <Link to="#" className="hover:text-accent transition-colors">
                                        {article.title}
                                    </Link>
                                </h3>
                                <p className="text-sm text-muted-foreground">{article.lead}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </section>
        </div>
    );
}
