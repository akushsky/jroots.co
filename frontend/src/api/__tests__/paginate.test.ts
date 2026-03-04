import {describe, it, expect} from "vitest";
import {getPaginationPages} from "../paginate";

describe("getPaginationPages", () => {
    it("returns all pages when total is small", () => {
        expect(getPaginationPages(0, 3)).toEqual([0, 1, 2]);
    });

    it("adds ellipsis for distant pages", () => {
        const pages = getPaginationPages(0, 10);
        expect(pages[0]).toBe(0);
        expect(pages).toContain("ellipsis");
        expect(pages[pages.length - 1]).toBe(9);
    });

    it("shows current page and neighbors", () => {
        const pages = getPaginationPages(5, 10);
        expect(pages).toContain(4);
        expect(pages).toContain(5);
        expect(pages).toContain(6);
    });

    it("handles single page", () => {
        expect(getPaginationPages(0, 1)).toEqual([0]);
    });
});
