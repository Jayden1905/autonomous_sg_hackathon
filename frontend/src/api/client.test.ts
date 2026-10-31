import { describe, expect, it } from "vitest";
import { readEvents } from "./client";
import type { StreamEvent } from "./client";

function bytes(text: string) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const byte of new TextEncoder().encode(text))
        controller.enqueue(new Uint8Array([byte]));
      controller.close();
    },
  });
}

describe("POST SSE transport", () => {
  it("decodes split UTF-8 and CRLF, skips heartbeats and unknown events", async () => {
    const events: StreamEvent[] = [];
    await readEvents(
      bytes(
        ': keepalive\r\n\r\nevent: future\r\ndata: {}\r\n\r\nevent: error\r\ndata: {"message":"Réponse interrupted",\r\ndata: "type":"AgentError"}\r\n\r\n',
      ),
      (e) => events.push(e),
    );
    expect(events).toEqual([
      {
        type: "error",
        data: { message: "Réponse interrupted", type: "AgentError" },
      },
    ]);
  });
  it("does not treat EOF after a proposal as a successful run", async () => {
    await expect(
      readEvents(
        bytes(
          'event: thinking\ndata: {"turn":1,"agent":"atc","action":"propose"}\n\n',
        ),
        () => undefined,
      ),
    ).rejects.toThrow("incomplete");
  });
  it("surfaces malformed JSON instead of silently skipping a result", async () => {
    await expect(
      readEvents(bytes("event: done\ndata: not-json\n\n"), () => undefined),
    ).rejects.toThrow();
  });
});
