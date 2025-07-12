import {BrowserRouter as Router, Routes, Route, Navigate} from "react-router-dom";
import {SearchPage} from "./components/SearchPage";
import AdminLogin from "./components/AdminLogin";
import AdminDashboard from "./components/AdminDashboard";
import {Heart, Mail, Info, X} from "lucide-react";
import {useEffect, useState} from "react";
import RegisterForm from "@/components/RegisterForm.tsx";
import VerifyPage from "@/components/VerifyPage.tsx";
import LoginForm from "@/components/LoginForm.tsx";

// @ts-ignore
function WelcomePopup({onClose}) {
    return (
        <div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex justify-center items-start sm:items-center z-50 p-4 py-8 overflow-y-auto">
            <div
                className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 md:p-8 relative text-gray-800 overflow-y-auto max-h-full">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-gray-500 hover:text-gray-800 transition-colors z-10"
                >
                    <X className="w-6 h-6"/>
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
                            <li>
                                Собираем в единую базу данных еврейские архивные материалы,
                                разбросанные по интернету
                            </li>
                            <li>
                                Индексируем списки, сканы документов и другие исторические материалы
                                из групп в Facebook, Telegram и других источников
                            </li>
                            <li>
                                Предоставляем удобный поиск по именам, датам, местам и ключевым
                                словам
                            </li>
                        </ul>
                    </div>

                    <div>
                        <h3 className="font-semibold text-lg mb-2">Почему это важно:</h3>
                        <p className="text-gray-700">
                            Ценные исторические материалы часто появляются в разных группах и
                            каналах, но быстро теряются в потоке информации. Наш поисковик
                            решает эту проблему, делая все материалы доступными для исследователей,
                            генеалогов и всех интересующихся еврейской историей.
                        </p>
                    </div>
                </div>

                <p className="mt-6 text-center font-medium text-gray-800">
                    Начните поиск прямо сейчас или поделитесь с нами новыми материалами для
                    пополнения базы данных!
                </p>
            </div>
        </div>
    );
}

function App() {
    const isAuthenticated = () => !!localStorage.getItem("token");
    const [showWelcome, setShowWelcome] = useState(false);

    useEffect(() => {
        const hasVisited = localStorage.getItem("hasVisitedSite");
        if (!hasVisited) {
            setShowWelcome(true);
            localStorage.setItem("hasVisitedSite", "true");
        }
    }, []);

    const handleClosePopup = () => {
        setShowWelcome(false);
    };

    return (
        <Router>
            {showWelcome && <WelcomePopup onClose={handleClosePopup}/>}

            <div className="min-h-screen bg-gray-50 py-10">
                <Routes>
                    <Route path="/" element={<SearchPage/>}/>
                    <Route path="/admin/login" element={<AdminLogin/>}/>
                    <Route path="/signup" element={<RegisterForm/>}/>
                    <Route path="/verify" element={<VerifyPage/>}/>
                    <Route path="/login" element={<LoginForm/>}/>
                    <Route
                        path="/admin/dashboard"
                        element={isAuthenticated() ? <AdminDashboard/> : <Navigate to="/admin/login"/>}
                    />
                </Routes>
            </div>
            <AboutBlock/>
            <DonationButton/>
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
                <Heart className="w-4 h-4 fill-red-600 text-red-600"/>
                Гешэфт
            </a>
        </div>
    );
}

function AboutBlock() {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="fixed bottom-4 left-4 z-50 text-sm text-gray-300">
            {/* Mobile collapse button */}
            <button
                onClick={() => setExpanded((prev) => !prev)}
                className="sm:hidden bg-black/60 backdrop-blur p-2 rounded-full shadow-md"
            >
                <Info className="w-4 h-4 text-white"/>
            </button>

            {/* Main content block (hidden on small unless expanded) */}
            <div
                className={`${
                    expanded ? "block" : "hidden"
                } sm:flex flex-col gap-1 mt-2 sm:mt-0 bg-black/60 backdrop-blur px-4 py-2 rounded-xl shadow-md text-gray-300`}
            >
                {/* Line 1: Title with Star of David */}
                <div className="flex items-center justify-center gap-2">
                    <span>Я знаю, чего хочет консул. А также — где это найти.</span>
                </div>

                {/* Line 2: Links */}
                <div className="flex flex-wrap gap-4 mt-1 items-center text-sm">
                    <div className="flex items-center gap-1 hover:text-white transition">
                        <a
                            href="https://t.me/namelles_one"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-gray-200 hover:text-white underline underline-offset-2 transition"
                        >
                            @Namelles_One
                        </a>
                    </div>

                    <div className="flex items-center gap-1 hover:text-white transition">
                        <Mail className="w-4 h-4"/>
                        <a
                            href="mailto:michael.akushsky@gmail.com"
                            className="hover:underline"
                        >
                            michael.akushsky@gmail.com
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default App;
