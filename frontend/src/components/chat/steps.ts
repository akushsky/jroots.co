const STEPS_PATTERN = /<steps>([\s\S]*?)<\/steps>/g;
const SEARCHLOG_PATTERN = /<searchlog>([\s\S]*?)<\/searchlog>/g;

export interface ExtractedSteps {
    /** One entry per <steps> block, or null when the content had none. */
    steps: string[] | null;
    /** Answer content with all <steps> blocks removed. */
    content: string;
}

/**
 * Split persisted assistant content into the visible answer and the
 * intermediate reasoning wrapped in <steps>...</steps> by the backend.
 */
export function extractSteps(content: string): ExtractedSteps {
    const parts: string[] = [];
    const cleaned = content
        .replace(STEPS_PATTERN, (_match, inner: string) => {
            const text = inner.trim();
            if (text) parts.push(text);
            return "";
        })
        .trim();
    return {steps: parts.length > 0 ? parts : null, content: cleaned};
}

export interface ExtractedSearchlog {
    /** Journal lines across all <searchlog> blocks, one trimmed line per entry. */
    lines: string[];
    /** Content with all <searchlog> blocks removed. */
    rest: string;
}

/**
 * Extract the agent's search journal (<searchlog>...</searchlog>) — its memory
 * between turns. Never shown raw in the answer bubble.
 */
export function extractSearchlog(content: string): ExtractedSearchlog {
    const lines: string[] = [];
    const rest = content
        .replace(SEARCHLOG_PATTERN, (_match, inner: string) => {
            for (const line of inner.split("\n")) {
                const trimmed = line.trim();
                if (trimmed) lines.push(trimmed);
            }
            return "";
        })
        .trim();
    return {lines, rest};
}
