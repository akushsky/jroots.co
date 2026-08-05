import "@testing-library/jest-dom/vitest";

// jsdom does not implement object URLs; components use them for scan thumbnails.
if (typeof URL.createObjectURL !== "function") {
    let objectUrlCounter = 0;
    URL.createObjectURL = () => `blob:mock-${++objectUrlCounter}`;
    URL.revokeObjectURL = () => {};
}

// jsdom has no ResizeObserver; Radix poppers/tooltips crash without it.
if (typeof globalThis.ResizeObserver !== "function") {
    globalThis.ResizeObserver = class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
    };
}
