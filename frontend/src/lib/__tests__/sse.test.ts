import {describe, expect, it} from "vitest";
import {SSEParser} from "../sse";

describe("SSEParser", () => {
    it("parses a single event", () => {
        const parser = new SSEParser();
        const events = parser.feed('event: token\ndata: {"text":"привет"}\n\n');
        expect(events).toEqual([{event: "token", data: '{"text":"привет"}'}]);
    });

    it("joins multiple data lines with a newline", () => {
        const parser = new SSEParser();
        const events = parser.feed("event: token\ndata: первая\ndata: вторая\n\n");
        expect(events).toEqual([{event: "token", data: "первая\nвторая"}]);
    });

    it("handles a line split across chunks", () => {
        const parser = new SSEParser();
        expect(parser.feed('event: tok')).toEqual([]);
        expect(parser.feed('en\ndata: {"te')).toEqual([]);
        const events = parser.feed('xt":"раз"}\n\n');
        expect(events).toEqual([{event: "token", data: '{"text":"раз"}'}]);
    });

    it("handles an event boundary split across chunks", () => {
        const parser = new SSEParser();
        expect(parser.feed('event: token\ndata: {"a":1}\n')).toEqual([]);
        const events = parser.feed('\nevent: done\ndata: {"ok":true}\n\n');
        expect(events).toEqual([
            {event: "token", data: '{"a":1}'},
            {event: "done", data: '{"ok":true}'},
        ]);
    });

    it("parses several events arriving in one chunk", () => {
        const parser = new SSEParser();
        const events = parser.feed(
            'event: token\ndata: {"text":"а"}\n\nevent: token\ndata: {"text":"б"}\n\n',
        );
        expect(events).toHaveLength(2);
        expect(events[1]).toEqual({event: "token", data: '{"text":"б"}'});
    });

    it("skips comment lines and keeps their data neighbours", () => {
        const parser = new SSEParser();
        const events = parser.feed(': keep-alive\nevent: usage\ndata: {"n":1}\n\n');
        expect(events).toEqual([{event: "usage", data: '{"n":1}'}]);
    });

    it("tolerates CRLF line endings", () => {
        const parser = new SSEParser();
        const events = parser.feed('event: token\r\ndata: {"x":2}\r\n\r\n');
        expect(events).toEqual([{event: "token", data: '{"x":2}'}]);
    });

    it("ignores events without data", () => {
        const parser = new SSEParser();
        expect(parser.feed("event: ping\n\n")).toEqual([]);
    });

    it("defaults the event name to message", () => {
        const parser = new SSEParser();
        const events = parser.feed('data: {"plain":true}\n\n');
        expect(events).toEqual([{event: "message", data: '{"plain":true}'}]);
    });

    it("flush parses a trailing event without blank-line terminator", () => {
        const parser = new SSEParser();
        parser.feed('event: done\ndata: {"message_id":"m1"}');
        expect(parser.flush()).toEqual([
            {event: "done", data: '{"message_id":"m1"}'},
        ]);
        expect(parser.flush()).toEqual([]);
    });
});
