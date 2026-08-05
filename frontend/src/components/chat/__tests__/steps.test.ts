import {describe, expect, it} from "vitest";
import {extractSearchlog, extractSteps} from "../steps";

describe("extractSteps", () => {
    it("extracts a single steps block from the answer", () => {
        const result = extractSteps("<steps>Искал в ревизиях</steps>Вот что нашёл.");
        expect(result.steps).toEqual(["Искал в ревизиях"]);
        expect(result.content).toBe("Вот что нашёл.");
    });

    it("keeps multiple steps blocks as separate entries and cleans the answer", () => {
        const result = extractSteps(
            "<steps>Шаг один</steps>Начало ответа. <steps>Шаг два</steps> Конец ответа.",
        );
        expect(result.steps).toEqual(["Шаг один", "Шаг два"]);
        expect(result.content).toBe("Начало ответа.  Конец ответа.");
    });

    it("handles multiline steps content as one entry", () => {
        const result = extractSteps("<steps>\nСтрока 1\nСтрока 2\n</steps>Ответ");
        expect(result.steps).toEqual(["Строка 1\nСтрока 2"]);
        expect(result.content).toBe("Ответ");
    });

    it("returns null steps and untouched content when no blocks present", () => {
        const result = extractSteps("Просто ответ без шагов.");
        expect(result.steps).toBeNull();
        expect(result.content).toBe("Просто ответ без шагов.");
    });

    it("ignores empty steps blocks", () => {
        const result = extractSteps("<steps>  </steps>Ответ");
        expect(result.steps).toBeNull();
        expect(result.content).toBe("Ответ");
    });
});

describe("extractSearchlog", () => {
    it("returns empty lines and untouched content when no block present", () => {
        const result = extractSearchlog("Просто ответ.");
        expect(result.lines).toEqual([]);
        expect(result.rest).toBe("Просто ответ.");
    });

    it("splits a multiline block into trimmed lines", () => {
        const result = extractSearchlog(
            "Ответ.\n<searchlog>\nsearch(toldot_cemetery, Клебанов Мордух) → 1 результатов\n\nsearch(yandex_archive, Клебанов) → 0 результатов\n</searchlog>",
        );
        expect(result.lines).toEqual([
            "search(toldot_cemetery, Клебанов Мордух) → 1 результатов",
            "search(yandex_archive, Клебанов) → 0 результатов",
        ]);
        expect(result.rest).toBe("Ответ.");
    });

    it("treats an empty block as no journal", () => {
        const result = extractSearchlog("Ответ.<searchlog>  \n </searchlog>");
        expect(result.lines).toEqual([]);
        expect(result.rest).toBe("Ответ.");
    });

    it("collects lines across multiple blocks and keeps error rows", () => {
        const result = extractSearchlog(
            "<searchlog>search(a, x) → 1 результатов</searchlog>Текст.<searchlog>search(b, y) → ошибка</searchlog>",
        );
        expect(result.lines).toEqual(["search(a, x) → 1 результатов", "search(b, y) → ошибка"]);
        expect(result.rest).toBe("Текст.");
    });
});
