import {BrowserRouter as Router, Routes, Route, Navigate} from "react-router-dom";
import SearchPage from "./components/SearchPage";
import AdminLogin from "./components/AdminLogin";
import AdminDashboard from "./components/AdminDashboard";
import {Heart} from "lucide-react";

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

export default App;
