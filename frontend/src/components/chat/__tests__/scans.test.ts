import {describe, expect, it} from "vitest";
import {MAX_SCAN_BYTES, SCAN_TOO_LARGE, SCAN_UNSUPPORTED, validateScanFile} from "../scans";

function makeFile(name: string, type: string, size: number): File {
    const file = new File(["x"], name, {type});
    Object.defineProperty(file, "size", {value: size});
    return file;
}

describe("validateScanFile", () => {
    it("accepts jpeg, png and tiff by mime type", () => {
        expect(validateScanFile(makeFile("a.jpg", "image/jpeg", 100))).toBeNull();
        expect(validateScanFile(makeFile("a.png", "image/png", 100))).toBeNull();
        expect(validateScanFile(makeFile("a.tiff", "image/tiff", 100))).toBeNull();
    });

    it("accepts a supported extension when the mime type is missing", () => {
        expect(validateScanFile(makeFile("scan.tif", "", 100))).toBeNull();
        expect(validateScanFile(makeFile("scan.JPEG", "", 100))).toBeNull();
    });

    it("rejects files over 10 MB", () => {
        expect(validateScanFile(makeFile("big.jpg", "image/jpeg", MAX_SCAN_BYTES + 1))).toBe(
            SCAN_TOO_LARGE,
        );
        expect(validateScanFile(makeFile("max.jpg", "image/jpeg", MAX_SCAN_BYTES))).toBeNull();
    });

    it("rejects unsupported formats", () => {
        expect(validateScanFile(makeFile("doc.pdf", "application/pdf", 100))).toBe(
            SCAN_UNSUPPORTED,
        );
        expect(validateScanFile(makeFile("anim.gif", "image/gif", 100))).toBe(SCAN_UNSUPPORTED);
    });
});
