import {Link, useLocation, useNavigate} from "react-router-dom";
import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import {useAuth} from "@/hooks/useAuth";
import {registrationEnabled} from "@/lib/registration";

interface AppHeaderProps {
    /** Line under the JRoots title. */
    subtitle?: string;
    className?: string;
}

const SECTIONS = [
    {to: "/", label: "Поиск"},
    {to: "/chat", label: "Ассистент"},
];

/**
 * Site chrome shared by Search and Chat: brand, section tabs, account.
 */
export function AppHeader({
    subtitle = "Поиск по еврейским архивным материалам",
    className,
}: AppHeaderProps) {
    const {user, logout} = useAuth();
    const navigate = useNavigate();
    const {pathname} = useLocation();

    return (
        <header className={cn("mb-6", className)}>
            <div className="flex items-start justify-between gap-4">
                <Link to="/" className="group min-w-0">
                    <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none transition-colors group-hover:text-accent">
                        JRoots
                    </h1>
                    <p className="mt-1.5 truncate text-sm text-muted-foreground">{subtitle}</p>
                </Link>

                {user ? (
                    <div className="flex shrink-0 items-center gap-2.5">
                        <span
                            aria-hidden
                            className="grid size-9 place-items-center rounded-full border border-border bg-card font-[family-name:var(--font-display)] text-base font-semibold sm:hidden"
                        >
                            {user.username.slice(0, 1).toUpperCase()}
                        </span>
                        <div className="hidden text-right leading-tight sm:block">
                            <div className="max-w-[14rem] truncate text-sm font-medium">
                                {user.username}
                            </div>
                            <div className="max-w-[14rem] truncate text-xs text-muted-foreground">
                                {user.email}
                            </div>
                        </div>
                        <Button variant="outline" size="sm" onClick={logout}>
                            Выйти
                        </Button>
                    </div>
                ) : (
                    <div className="flex shrink-0 gap-2">
                        <Button variant="outline" size="sm" onClick={() => navigate("/login")}>
                            Вход
                        </Button>
                        {registrationEnabled && (
                            <Button size="sm" onClick={() => navigate("/signup")}>
                                Регистрация
                            </Button>
                        )}
                    </div>
                )}
            </div>

            <nav aria-label="Разделы" className="mt-5 flex items-center gap-6 border-b border-border">
                {SECTIONS.map((section) => {
                    const active =
                        section.to === "/" ? pathname === "/" : pathname.startsWith(section.to);
                    return (
                        <Link
                            key={section.to}
                            to={section.to}
                            aria-current={active ? "page" : undefined}
                            className={cn(
                                "-mb-px border-b-2 pb-2.5 text-sm transition-colors",
                                active
                                    ? "border-accent font-medium text-foreground"
                                    : "border-transparent text-muted-foreground hover:text-foreground",
                            )}
                        >
                            {section.label}
                        </Link>
                    );
                })}
            </nav>
        </header>
    );
}
