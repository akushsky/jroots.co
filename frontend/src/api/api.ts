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

export interface SearchFilters {
    source_id?: number;
    sort?: "relevance" | "date";
    mode?: "fuzzy" | "exact";
}

export const searchObjects = async (
    q: string,
    page: number,
    pageSize: number,
    signal?: AbortSignal,
    filters?: SearchFilters,
) => {
    const params = new URLSearchParams({
        q,
        skip: String(page * pageSize),
        limit: String(pageSize),
    });
    if (filters?.source_id) params.set("source_id", String(filters.source_id));
    if (filters?.sort && filters.sort !== "relevance") params.set("sort", filters.sort);
    if (filters?.mode && filters.mode !== "fuzzy") params.set("mode", filters.mode);
    return (await apiClient.get(`/search?${params}`, {signal})).data;
};

export const fetchSources = async () =>
    (await apiClient.get("/sources")).data as Array<{ id: number; source_name: string; description: string | null }>;

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

export const forgotPassword = async (email: string) =>
    (await apiClient.post("/forgot-password", {email})).data;

export const resetPassword = async (token: string, newPassword: string) =>
    (await apiClient.post("/reset-password", {token, new_password: newPassword})).data;

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
