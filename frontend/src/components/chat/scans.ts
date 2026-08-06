/** Client-side rules for chat scan uploads (mirror of the backend contract). */

export const MAX_SCAN_BYTES = 10 * 1024 * 1024;

export const SCAN_ACCEPT = "image/jpeg,image/png,image/tiff,.jpg,.jpeg,.png,.tif,.tiff";

const ACCEPTED_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/tiff"]);
// Browsers often leave file.type empty for .tif/.tiff — fall back to the extension.
const ACCEPTED_EXTENSION = /\.(jpe?g|png|tiff?)$/i;

export const SCAN_TOO_LARGE = "Файл больше 10 МБ — сожмите или обрежьте скан";
export const SCAN_UNSUPPORTED = "Поддерживаются только JPEG, PNG и TIFF";

/** Returns an error message for a file that must not be uploaded, null when valid. */
export function validateScanFile(file: File): string | null {
    if (file.size > MAX_SCAN_BYTES) return SCAN_TOO_LARGE;
    if (!ACCEPTED_MIME_TYPES.has(file.type) && !ACCEPTED_EXTENSION.test(file.name)) {
        return SCAN_UNSUPPORTED;
    }
    return null;
}

export interface ScanAttachment {
    localId: string;
    fileName: string;
    /** Object URL of the local file — shown as the chip/bubble thumbnail. */
    previewUrl: string;
    status: "uploading" | "done" | "error";
    /** Backend scan id, present once status is "done". */
    scanId?: number;
    /** OCR confidence from the backend ("low" → «неуверенное чтение» badge on the chip). */
    confidence?: string;
    /** Short failure reason rendered inline under the chip. */
    errorText?: string;
    /** Failure kinds with their own UI treatment (402 → clickable paywall chip). */
    errorCode?: "no_scans_left";
}
