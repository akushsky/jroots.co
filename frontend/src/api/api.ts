import axios from "axios";

export const apiClient = axios.create({
    baseURL: "/api",
});

// Add JWT token automatically
apiClient.interceptors.request.use((config) => {
    const token = localStorage.getItem("token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

export const searchObjects = async (q: string, page: number, pageSize: number) =>
    (await apiClient.get(`/search?q=${encodeURIComponent(q)}&skip=${page * pageSize}&limit=${pageSize}`)).data;

export const fetchObjects = async (page: number, pageSize: number) =>
    (await apiClient.get(`/admin/objects?skip=${page * pageSize}&limit=${pageSize}`)).data;

export const adminLogin = async (username: string, password: string) =>
    (await apiClient.post("/admin/login", new URLSearchParams({username, password}))).data;

export const createSearchObject = async (formData: FormData) =>
    (await apiClient.post("/admin/objects", formData)).data;

export const updateSearchObject = async (objectId: number, formData: FormData) =>
    (await apiClient.put(`/admin/objects/${objectId}`, formData)).data;

export const deleteSearchObject = async (objectId: number) =>
    (await apiClient.delete(`/admin/objects/${objectId}`)).data;
