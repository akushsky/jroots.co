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
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-900 border-t-transparent" />
        </div>
    );
}

interface WelcomePopupProps {
    onClose: () => void;
}

function WelcomePopup({onClose}: WelcomePopupProps) {
    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex justify-center items-start sm:items-center z-50 p-4 py-8 overflow-y-auto">
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 md:p-8 relative text-gray-800 overflow-y-auto max-h-full">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-gray-500 hover:text-gray-800 transition-colors z-10"
                    aria-label="Закрыть"
                >
                    <X className="w-6 h-6" />
                </button>

                <h2 className="text-2xl font-bold mb-4 text-center">
                    Архивный поисковик еврейских материалов
                </h2>

                <p className="mb-6 text-center text-gray-600">
                    Добро пожаловать на наш специализированный поисковый ресурс, созданный для
                    систематизации и поиска разрозненных еврейских архивных материалов!
                </p>

                <div className="space-y-4">
                    <div>
                        <h3 className="font-semibold text-lg mb-2">Что мы делаем:</h3>
                        <ul className="list-disc list-inside space-y-1 text-gray-700">
                            <li>Собираем в единую базу данных еврейские архивные материалы, разбросанные по интернету</li>
                            <li>Индексируем списки, сканы документов и другие исторические материалы из групп в Facebook, Telegram и других источников</li>
                            <li>Предоставляем удобный поиск по именам, датам, местам и ключевым словам</li>
                        </ul>
                    </div>

                    <div>
                        <h3 className="font-semibold text-lg mb-2">Почему это важно:</h3>
                        <p className="text-gray-700">
                            Ценные исторические материалы часто появляются в разных группах и каналах, но быстро
                            теряются в потоке информации. Наш поисковик решает эту проблему, делая все материалы
                            доступными для исследователей, генеалогов и всех интересующихся еврейской историей.
                        </p>
                    </div>
                </div>

                <p className="mt-6 text-center font-medium text-gray-800">
                    Начните поиск прямо сейчас или поделитесь с нами новыми материалами для пополнения базы данных!
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
            <h1 className="text-4xl font-bold mb-4">404</h1>
            <p className="text-gray-600 mb-4">Страница не найдена</p>
            <a href="/" className="text-indigo-600 hover:underline">На главную</a>
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
            <div className="min-h-screen bg-gray-50 py-10">
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
            <AboutBlock />
            <DonationButton />
        </>
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

function DonationButton() {
    return (
        <div className="fixed bottom-4 right-4 z-50">
            <a
                href="https://buymeacoffee.com/akushsky"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 bg-yellow-500 hover:bg-yellow-600 text-black font-semibold rounded-full shadow-lg transition-all"
            >
                <Heart className="w-4 h-4 fill-red-600 text-red-600" />
                Гешэфт
            </a>
        </div>
    );
}

function AboutBlock() {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="fixed bottom-4 left-4 z-50 text-sm text-gray-300">
            <button
                onClick={() => setExpanded((prev) => !prev)}
                className="sm:hidden bg-black/60 backdrop-blur p-2 rounded-full shadow-md"
                aria-label="Информация о сайте"
                aria-expanded={expanded}
            >
                <Info className="w-4 h-4 text-white" />
            </button>

            <div
                className={`${expanded ? "block" : "hidden"} sm:flex flex-col gap-1 mt-2 sm:mt-0 bg-black/60 backdrop-blur px-4 py-2 rounded-xl shadow-md text-gray-300`}
            >
                <div className="flex items-center justify-center gap-2">
                    <span>Я знаю, чего хочет консул. А также — где это найти.</span>
                </div>

                <div className="flex flex-wrap gap-4 mt-1 items-center text-sm">
                    <a
                        href="https://t.me/namelles_one"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-200 hover:text-white underline underline-offset-2 transition"
                    >
                        @Namelles_One
                    </a>

                    <div className="flex items-center gap-1 hover:text-white transition">
                        <Mail className="w-4 h-4" />
                        <a href="mailto:michael.akushsky@gmail.com" className="hover:underline">
                            michael.akushsky@gmail.com
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default App;
