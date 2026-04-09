import {lazy, Suspense, useEffect, useState} from "react";
import {BrowserRouter as Router, Navigate, Route, Routes} from "react-router-dom";
import {Heart, Info, Mail, X} from "lucide-react";
import {AuthProvider} from "@/contexts/AuthContext";
import {useAuth} from "@/hooks/useAuth";

const SearchPage = lazy(() => import("@/components/SearchPage"));
const AdminLogin = lazy(() => import("@/components/AdminLogin"));
const AdminDashboard = lazy(() => import("@/components/AdminDashboard"));
const RegisterForm = lazy(() => import("@/components/RegisterForm"));
const VerifyPage = lazy(() => import("@/components/VerifyPage"));
const LoginForm = lazy(() => import("@/components/LoginForm"));
const ForgotPasswordForm = lazy(() => import("@/components/ForgotPasswordForm"));
const ResetPasswordForm = lazy(() => import("@/components/ResetPasswordForm"));

function PageFallback() {
    return (
        <div className="flex items-center justify-center min-h-[50vh]">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-foreground/20 border-t-foreground/60" />
        </div>
    );
}

interface WelcomePopupProps {
    onClose: () => void;
}

function WelcomePopup({onClose}: WelcomePopupProps) {
    return (
        <div className="fixed inset-0 bg-foreground/40 backdrop-blur-sm flex justify-center items-start sm:items-center z-50 p-4 py-8 overflow-y-auto">
            <div className="bg-card rounded-lg shadow-xl max-w-2xl w-full p-8 md:p-10 relative overflow-y-auto max-h-full border-t-2 border-accent">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-muted-foreground hover:text-foreground transition-colors z-10"
                    aria-label="Закрыть"
                >
                    <X className="w-5 h-5" />
                </button>

                <h2 className="text-3xl font-bold mb-4 text-center">
                    Архивный поисковик еврейских материалов
                </h2>

                <p className="mb-8 text-center text-muted-foreground">
                    Добро пожаловать на специализированный ресурс для поиска
                    разрозненных еврейских архивных материалов.
                </p>

                <div className="space-y-6">
                    <div>
                        <h3 className="font-semibold text-lg mb-2">Что мы делаем</h3>
                        <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                            <li>Собираем в единую базу данных еврейские архивные материалы, разбросанные по интернету</li>
                            <li>Индексируем списки, сканы документов и другие исторические материалы из различных источников</li>
                            <li>Предоставляем удобный поиск по именам, датам, местам и ключевым словам</li>
                        </ul>
                    </div>

                    <div>
                        <h3 className="font-semibold text-lg mb-2">Почему это важно</h3>
                        <p className="text-muted-foreground">
                            Ценные исторические материалы часто появляются в разных группах и каналах, но быстро
                            теряются в потоке информации. Наш поисковик делает все материалы
                            доступными для исследователей, генеалогов и всех интересующихся еврейской историей.
                        </p>
                    </div>
                </div>

                <p className="mt-8 text-center font-medium text-sm text-muted-foreground">
                    Начните поиск прямо сейчас или поделитесь с нами новыми материалами для пополнения базы.
                </p>
            </div>
        </div>
    );
}

function ProtectedAdminRoute() {
    const {isAuthenticated, user} = useAuth();
    if (!isAuthenticated) return <Navigate to="/admin/login" />;
    if (!user?.is_admin) return <Navigate to="/" />;
    return (
        <Suspense fallback={<PageFallback />}>
            <AdminDashboard />
        </Suspense>
    );
}

function NotFound() {
    return (
        <div className="max-w-md mx-auto mt-20 text-center">
            <h1 className="text-5xl font-bold mb-4">404</h1>
            <p className="text-muted-foreground mb-4">Страница не найдена</p>
            <a href="/" className="text-accent hover:underline">На главную</a>
        </div>
    );
}

function AppRoutes() {
    const [showWelcome, setShowWelcome] = useState(false);

    useEffect(() => {
        const hasVisited = localStorage.getItem("hasVisitedSite");
        if (!hasVisited) {
            setShowWelcome(true);
            localStorage.setItem("hasVisitedSite", "true");
        }
    }, []);

    return (
        <>
            {showWelcome && <WelcomePopup onClose={() => setShowWelcome(false)} />}
            <div className="min-h-screen py-10">
                <Suspense fallback={<PageFallback />}>
                    <Routes>
                        <Route path="/" element={<SearchPage />} />
                        <Route path="/admin/login" element={<AdminLogin />} />
                        <Route path="/signup" element={<RegisterForm />} />
                        <Route path="/verify" element={<VerifyPage />} />
                        <Route path="/login" element={<LoginForm />} />
                        <Route path="/forgot-password" element={<ForgotPasswordForm />} />
                        <Route path="/reset" element={<ResetPasswordForm />} />
                        <Route path="/admin/dashboard" element={<ProtectedAdminRoute />} />
                        <Route path="*" element={<NotFound />} />
                    </Routes>
                </Suspense>
            </div>
            <Footer />
        </>
    );
}

function Footer() {
    const [expanded, setExpanded] = useState(false);

    return (
        <footer className="fixed bottom-0 left-0 right-0 z-50">
            <div className="flex items-center justify-between px-4 py-2 text-xs text-muted-foreground">
                {/* About — left */}
                <div>
                    <button
                        onClick={() => setExpanded((prev) => !prev)}
                        className="sm:hidden p-1.5 rounded-full bg-card/80 backdrop-blur border border-border shadow-sm"
                        aria-label="Информация о сайте"
                        aria-expanded={expanded}
                    >
                        <Info className="w-3.5 h-3.5" />
                    </button>

                    <div className={`${expanded ? "block" : "hidden"} sm:flex items-center gap-3 bg-card/80 backdrop-blur px-3 py-1.5 rounded-full border border-border shadow-sm`}>
                        <span className="italic hidden md:inline">Я знаю, чего хочет консул. А также — где это найти.</span>
                        <a
                            href="https://t.me/namelles_one"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:text-foreground transition-colors"
                        >
                            @Namelles_One
                        </a>
                        <a href="mailto:michael.akushsky@gmail.com" className="hidden sm:flex items-center gap-1 hover:text-foreground transition-colors">
                            <Mail className="w-3 h-3" />
                            michael.akushsky@gmail.com
                        </a>
                    </div>
                </div>

                {/* Donation — right */}
                <a
                    href="https://buymeacoffee.com/akushsky"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-card/80 backdrop-blur border border-border rounded-full shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                >
                    <Heart className="w-3 h-3 fill-red-500 text-red-500" />
                    <span>Гешэфт</span>
                </a>
            </div>
        </footer>
    );
}

function App() {
    return (
        <Router>
            <AuthProvider>
                <AppRoutes />
            </AuthProvider>
        </Router>
    );
}

export default App;
