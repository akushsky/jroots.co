import {describe, expect, it} from "vitest";
import {extractSteps} from "../steps";

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
