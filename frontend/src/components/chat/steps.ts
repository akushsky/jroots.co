const STEPS_PATTERN = /<steps>([\s\S]*?)<\/steps>/g;

export interface ExtractedSteps {
    /** Joined step text, or null when the content had no <steps> blocks. */
    steps: string | null;
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
    return {steps: parts.length > 0 ? parts.join("\n\n") : null, content: cleaned};
}
