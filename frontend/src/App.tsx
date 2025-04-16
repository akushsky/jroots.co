import {BrowserRouter as Router, Routes, Route, Navigate} from "react-router-dom";
import SearchPage from "./components/SearchPage";
import AdminLogin from "./components/AdminLogin";
import AdminDashboard from "./components/AdminDashboard";
import {Heart, Mail, Info} from "lucide-react";
import {useState} from "react";

function App() {
    const isAuthenticated = () => !!localStorage.getItem("token");

    return (
        <Router>
            <div className="min-h-screen bg-gray-50 py-10">
                <Routes>
                    <Route path="/" element={<SearchPage/>}/>
                    <Route path="/admin/login" element={<AdminLogin/>}/>
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
                        <Mail className="w-4 h-4" />
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
