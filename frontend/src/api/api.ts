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

export const userRegister = async (username: string, email: string, password: string, captchaToken: string) =>
    (await apiClient.post("/register", {
        "username": username,
        "email": email,
        "password": password,
        "captcha_token": captchaToken
    })).data;

export const userLogin = async (email: string, password: string) =>
    (await apiClient.post("/login", new URLSearchParams({
        username: email,
        password,
    }))).data;

interface ImageCacheEntry {
    etag: string;
    blobUrl: string;
}

const imageCache: Record<number, ImageCacheEntry> = {};

export async function fetchImage(imageId: number): Promise<string | null> {
    const cached = imageCache[imageId];
    const headers: Record<string, string> = {};

    if (cached?.etag) {
        headers['If-None-Match'] = cached.etag;
    }

    try {
        const response = await apiClient.get(`/images/${imageId}`, {
            responseType: "blob",
            headers,
            validateStatus: (status) => status === 200 || status === 304
        });

        if (response.status === 304 && cached) {
            console.log(`Using cached image for ${imageId}`);
            return cached.blobUrl;
        }

        const newEtag = response.headers['etag'];
        const newBlobUrl = URL.createObjectURL(response.data);

        // Revoke old blob if exists
        if (cached?.blobUrl) {
            URL.revokeObjectURL(cached.blobUrl);
        }

        // Cache new blob and etag
        imageCache[imageId] = {
            etag: newEtag,
            blobUrl: newBlobUrl,
        };

        return newBlobUrl;
    } catch (error) {
        console.error("Error fetching image:", error);
        return null;
    }
}

export function clearImageCache() {
    Object.values(imageCache).forEach(entry => {
        URL.revokeObjectURL(entry.blobUrl);
    });
    Object.keys(imageCache).forEach(key => {
        delete imageCache[+key];
    });
}