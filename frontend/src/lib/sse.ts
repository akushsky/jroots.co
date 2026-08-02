export interface SSEEvent {
    event: string;
    data: string;
}

const EVENT_SEPARATOR = /\r?\n\r?\n/;

function parseBlock(block: string): SSEEvent | null {
    let event = "message";
    const dataLines: string[] = [];

    for (const rawLine of block.split(/\r?\n/)) {
        if (!rawLine || rawLine.startsWith(":")) continue;
        const colon = rawLine.indexOf(":");
        const field = colon === -1 ? rawLine : rawLine.slice(0, colon);
        let value = colon === -1 ? "" : rawLine.slice(colon + 1);
        if (value.startsWith(" ")) value = value.slice(1);
        if (field === "event") {
            event = value;
        } else if (field === "data") {
            dataLines.push(value);
        }
    }

    if (dataLines.length === 0) return null;
    return {event, data: dataLines.join("\n")};
}

/**
 * Incremental SSE parser. Feed raw text chunks as they arrive from the
 * stream; complete events come back. Handles lines split across chunks,
 * CRLF endings, comment lines and multi-line `data:` fields.
 */
export class SSEParser {
    private buffer = "";

    feed(chunk: string): SSEEvent[] {
        this.buffer += chunk;
        const events: SSEEvent[] = [];

        for (;;) {
            const match = EVENT_SEPARATOR.exec(this.buffer);
            if (!match) break;
            const block = this.buffer.slice(0, match.index);
            this.buffer = this.buffer.slice(match.index + match[0].length);
            const parsed = parseBlock(block);
            if (parsed) events.push(parsed);
        }

        return events;
    }

    /** Parse whatever is left after the stream closes without a trailing blank line. */
    flush(): SSEEvent[] {
        const rest = this.buffer;
        this.buffer = "";
        if (!rest.trim()) return [];
        const parsed = parseBlock(rest);
        return parsed ? [parsed] : [];
    }
}
