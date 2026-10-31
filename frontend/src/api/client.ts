import type { components } from "../../../contracts/types";

export type Schemas = components["schemas"];
export type Events = Schemas["StreamEvents"];
export type StreamEvent = {
  [K in keyof Events]: { type: K; data: Events[K] };
}[keyof Events];
const base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
export const apiUrl = (path: string) => `${base}${path}`;

async function checked(response: Response) {
  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      detail = JSON.stringify(JSON.parse(body).detail ?? body);
    } catch {
      /* Plain HTTP error. */
    }
    throw new Error(
      `API ${response.status}: ${detail.slice(0, 400) || response.statusText}`,
    );
  }
  return response;
}

export async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  return (await checked(await fetch(apiUrl(path), { signal }))).json();
}

const eventNames = new Set([
  "started",
  "thinking",
  "tool_call",
  "guardrail",
  "proposal",
  "evaluation",
  "response",
  "turn_complete",
  "done",
  "error",
]);

/** POST SSE: tolerate network chunk boundaries, UTF-8, CRLF and comment heartbeats. */
export async function readEvents(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    terminal = false;
  const dispatch = (frame: string) => {
    let name = "";
    const data: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (!eventNames.has(name) || !data.length) return;
    const payload = JSON.parse(data.join("\n"));
    if (!payload || typeof payload !== "object")
      throw new Error("Invalid negotiation event.");
    onEvent({ type: name, data: payload } as StreamEvent);
    terminal = name === "done" || name === "error";
  };
  try {
    while (!terminal) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let match: RegExpExecArray | null;
      while (!terminal && (match = /\r?\n\r?\n/.exec(buffer))) {
        dispatch(buffer.slice(0, match.index));
        buffer = buffer.slice(match.index + match[0].length);
      }
      if (done) {
        if (!terminal && buffer.trim()) dispatch(buffer);
        if (!terminal)
          throw new Error(
            "Connection ended before a final result. This run is incomplete.",
          );
        break;
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export async function negotiate(
  request: Schemas["NegotiateRequest"],
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await checked(
    await fetch(apiUrl("/negotiate/stream"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(request),
      signal,
    }),
  );
  if (
    !response.body ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  ) {
    throw new Error(
      "The server did not return a negotiation stream. Check the API connection.",
    );
  }
  await readEvents(response.body, onEvent);
}
