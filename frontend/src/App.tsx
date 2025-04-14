import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import SearchPage from "./components/SearchPage";
import AdminLogin from "./components/AdminLogin";
import AdminDashboard from "./components/AdminDashboard";

function App() {
    const isAuthenticated = () => !!localStorage.getItem("token");

    return (
        <Router>
            <div className="min-h-screen bg-gray-50 py-10">
                <Routes>
                    <Route path="/" element={<SearchPage />} />
                    <Route path="/admin/login" element={<AdminLogin />} />
                    <Route
                        path="/admin/dashboard"
                        element={isAuthenticated() ? <AdminDashboard /> : <Navigate to="/admin/login" />}
                    />
                </Routes>
            </div>
        </Router>
    );
}

export default App;
