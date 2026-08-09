import {useState, type ReactNode} from "react";
import {Link, useNavigate} from "react-router-dom";
import {ArrowRight, BookOpen, FileSearch, MessagesSquare, ScrollText, Search} from "lucide-react";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {Paywall} from "@/components/chat/Paywall";
import {BrandMark} from "@/components/shared/BrandMark";
import {PageContainer} from "@/components/shared/PageContainer";
import {SuggestionChip} from "@/components/shared/SuggestionChip";
import {useAuth} from "@/hooks/useAuth";
import {registrationEnabled} from "@/lib/registration";

// The same starters the assistant offers on an empty chat, so the hand-off feels continuous.
const HINTS = [
    "Рабиновичи из Бердичева, конец XIX века",
    "Дед служил в армии, погиб в 1943 под Сталинградом",
    "Семья Штерн, Кишинёв, эвакуация в 1941",
];

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

function SectionHeading({children}: { children: ReactNode }) {
    return (
        <h2 className="text-center font-display text-2xl font-semibold sm:text-3xl">{children}</h2>
    );
}

export default function LandingPage() {
    const navigate = useNavigate();
    const [query, setQuery] = useState("");
    const {isAuthenticated} = useAuth();
    // Guests: signup when open, otherwise login (invite-only beta). Logged-in → chat.
    const authCtaHref = isAuthenticated ? "/chat" : registrationEnabled ? "/signup" : "/login";
    const authCtaLabel = isAuthenticated
        ? "Перейти в чат"
        : registrationEnabled
          ? "Создать аккаунт"
          : "Войти";

    const submit = (e: React.FormEvent) => {
        e.preventDefault();
        const text = query.trim();
        if (!text) return;
        navigate(`/chat?q=${encodeURIComponent(text)}`);
    };

    return (
        <PageContainer measure="workspace">
            {/* Marketing chrome: same brand block and rule as AppHeader, minus the
                product tabs — guests have nothing to switch between yet. */}
            <header className="mb-10 flex items-center justify-between gap-4 border-b border-border pb-5 sm:mb-14">
                <BrandMark align="start" />
                <div className="flex shrink-0 items-center gap-2">
                    {!isAuthenticated && (
                        <Button asChild variant="outline" size="sm" className="hidden sm:inline-flex">
                            <Link to="/login">Вход</Link>
                        </Button>
                    )}
                    <Button asChild size="sm">
                        <Link to={authCtaHref} data-testid="header-auth-cta">{authCtaLabel}</Link>
                    </Button>
                </div>
            </header>

            {/* Same reading measure as search results and chat answers. */}
            <div className="mx-auto w-full max-w-reading space-y-14 pb-16 sm:space-y-20">
                {/* Hero */}
                <section className="space-y-6 text-center">
                    <h1 className="font-display text-4xl font-bold leading-tight text-balance sm:text-5xl">
                        Найдите документы вашей семьи для репатриации
                    </h1>
                    <p className="mx-auto max-w-xl text-muted-foreground text-pretty">
                        Ассистент ищет метрики, ревизские сказки, списки захоронений и эвакуации
                        по десяткам архивов — и показывает записи, которые принимает консульство.
                    </p>

                    <form onSubmit={submit} className="mx-auto flex w-full max-w-xl flex-col gap-2 sm:flex-row">
                        <div className="relative flex-1">
                            <Search className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Расскажите, кого ищете"
                                aria-label="Кого ищете"
                                className="h-12 bg-card pl-11 text-base shadow-xs"
                            />
                        </div>
                        <Button type="submit" size="lg" className="h-12 shrink-0" disabled={!query.trim()}>
                            Начать поиск
                            <ArrowRight />
                        </Button>
                    </form>

                    <div className="flex flex-wrap justify-center gap-2">
                        {HINTS.map((hint) => (
                            <SuggestionChip
                                key={hint}
                                onClick={() => setQuery(hint)}
                                className="px-3 py-1 text-xs"
                            >
                                {hint}
                            </SuggestionChip>
                        ))}
                    </div>

                    <div className="flex flex-col items-center gap-2 pt-2">
                        <Button asChild variant="outline">
                            <Link to={authCtaHref} data-testid="hero-auth-cta">{authCtaLabel}</Link>
                        </Button>
                        <p className="text-xs text-muted-foreground">
                            Первые поиски — бесплатно, без карты.
                        </p>
                    </div>
                </section>

                {/* Two tools */}
                <section className="space-y-5">
                    <SectionHeading>Два инструмента</SectionHeading>
                    <div className="grid gap-4 md:grid-cols-2">
                        <Card className="py-0 transition-colors hover:border-accent">
                            <CardContent className="flex h-full flex-col gap-3 p-5">
                                <MessagesSquare className="size-6 text-accent" />
                                <h3 className="font-display text-xl font-semibold">AI-ассистент</h3>
                                <p className="flex-1 text-sm text-muted-foreground">
                                    Диалог вместо архивных каталогов: ассистент ищет за вас,
                                    показывает записи и распознаёт сканы документов. Не нужно быть
                                    генеалогом — достаточно семейных преданий.
                                </p>
                                <Button asChild className="self-start">
                                    <Link to={authCtaHref} data-testid="tool-chat-cta">Начать поиск</Link>
                                </Button>
                            </CardContent>
                        </Card>
                        <Card className="py-0 transition-colors hover:border-accent">
                            <CardContent className="flex h-full flex-col gap-3 p-5">
                                <Search className="size-6 text-accent" />
                                <div className="space-y-1">
                                    <h3 className="font-display text-xl font-semibold">
                                        Профессиональный поиск по архивам
                                    </h3>
                                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                                        Проект «Внезапные евреи»
                                    </p>
                                </div>
                                <p className="flex-1 text-sm text-muted-foreground">
                                    Прямой поиск по агрегированной базе фондов и сканов —
                                    для исследователей, которые хотят копать сами.
                                </p>
                                <Button asChild variant="secondary" className="self-start">
                                    <Link to="/" data-testid="tool-search-cta">Открыть поиск</Link>
                                </Button>
                            </CardContent>
                        </Card>
                    </div>
                </section>

                {/* How it works */}
                <section className="space-y-6">
                    <SectionHeading>Как это работает</SectionHeading>
                    <ol className="grid gap-6 sm:grid-cols-3">
                        {STEPS.map((step, index) => (
                            <li key={step.title} className="space-y-2">
                                <div className="flex items-start gap-3">
                                    <span
                                        aria-hidden
                                        className="grid size-8 shrink-0 place-items-center rounded-full border border-border bg-card font-display text-base font-semibold text-accent"
                                    >
                                        {index + 1}
                                    </span>
                                    <h3 className="pt-1 font-display text-lg font-semibold leading-snug">
                                        {step.title}
                                    </h3>
                                </div>
                                <p className="text-sm text-muted-foreground pl-11">
                                    {step.text}
                                </p>
                            </li>
                        ))}
                    </ol>
                </section>

                {/* Example dialogs — same bubbles the assistant renders. */}
                <section className="space-y-5">
                    <SectionHeading>Так выглядит поиск</SectionHeading>
                    <div className="grid gap-4">
                        {EXAMPLES.map((example) => (
                            <Card key={example.label} className="py-0">
                                <CardContent className="flex flex-col gap-3 p-5">
                                    <span className="text-xs uppercase tracking-wide text-muted-foreground">
                                        {example.label}
                                    </span>
                                    <div className="flex justify-end">
                                        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm leading-relaxed text-accent-foreground shadow-xs md:max-w-[75%]">
                                            {example.question}
                                        </div>
                                    </div>
                                    <div className="flex justify-start">
                                        <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-secondary px-4 py-2.5 text-sm leading-relaxed text-secondary-foreground shadow-xs md:max-w-[75%]">
                                            {example.answer}
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </section>

                {/* Tariffs */}
                <section>
                    <Paywall
                        title="Тарифы"
                        description="Начните бесплатно, продолжите — когда увидите первые записи своей семьи."
                    />
                </section>

                {/* SEO articles */}
                <section className="space-y-5">
                    <SectionHeading>Полезные материалы</SectionHeading>
                    <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card shadow-xs">
                        {ARTICLES.map((article) => (
                            <li key={article.title}>
                                <Link to="#" className="group block px-5 py-4 transition-colors hover:bg-secondary/40">
                                    <h3 className="font-semibold transition-colors group-hover:text-accent">
                                        {article.title}
                                    </h3>
                                    <p className="mt-1 text-sm text-muted-foreground">{article.lead}</p>
                                </Link>
                            </li>
                        ))}
                    </ul>
                </section>
            </div>
        </PageContainer>
    );
}
