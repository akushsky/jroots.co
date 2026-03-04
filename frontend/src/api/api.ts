import axios from "axios";

export const apiClient = axios.create({
    baseURL: "/api",
});

apiClient.interceptors.request.use((config) => {
    const token = localStorage.getItem("token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem("token");
            window.dispatchEvent(new CustomEvent("auth:expired"));
        }
        return Promise.reject(error);
    },
);

export const searchObjects = async (
    q: string,
    page: number,
    pageSize: number,
    signal?: AbortSignal,
) => (await apiClient.get(`/search?q=${encodeURIComponent(q)}&skip=${page * pageSize}&limit=${pageSize}`, {signal})).data;

export const fetchObjects = async (page: number, pageSize: number) =>
    (await apiClient.get(`/admin/objects?skip=${page * pageSize}&limit=${pageSize}`)).data;

export const createSearchObject = async (formData: FormData) =>
    (await apiClient.post("/admin/objects", formData)).data;

export const updateSearchObject = async (objectId: number, formData: FormData) =>
    (await apiClient.put(`/admin/objects/${objectId}`, formData)).data;

export const deleteSearchObject = async (objectId: number) =>
    (await apiClient.delete(`/admin/objects/${objectId}`)).data;

export const userRegister = async (
    username: string,
    email: string,
    password: string,
    telegramUsername: string,
    captchaToken: string,
) =>
    (await apiClient.post("/register", {
        username,
        email,
        password,
        telegram_username: telegramUsername,
        captcha_token: captchaToken,
    })).data;

export const userLogin = async (email: string, password: string) =>
    (await apiClient.post("/login", new URLSearchParams({username: email, password}))).data;

export const requestAccess = async (imageId: number, searchTextContent: string) =>
    (await apiClient.post("/request_access", {
        image_id: imageId,
        search_text_content: searchTextContent,
    })).data;

interface ImageCacheEntry {
    etag: string;
    blobUrl: string;
}

const imageCache: Record<number, ImageCacheEntry> = {};

export async function fetchImage(imageId: number): Promise<string | null> {
    const cached = imageCache[imageId];
    const headers: Record<string, string> = {};

    if (cached?.etag) {
        headers["If-None-Match"] = cached.etag;
    }

    try {
        const response = await apiClient.get(`/images/${imageId}`, {
            responseType: "blob",
            headers,
            validateStatus: (status) => status === 200 || status === 304,
        });

        if (response.status === 304 && cached) {
            return cached.blobUrl;
        }

        const newEtag = response.headers["etag"];
        const newBlobUrl = URL.createObjectURL(response.data);

        if (cached?.blobUrl) {
            URL.revokeObjectURL(cached.blobUrl);
        }

        imageCache[imageId] = {etag: newEtag, blobUrl: newBlobUrl};
        return newBlobUrl;
    } catch {
        return null;
    }
}

export function clearImageCache() {
    Object.values(imageCache).forEach((entry) => URL.revokeObjectURL(entry.blobUrl));
    Object.keys(imageCache).forEach((key) => delete imageCache[+key]);
}
