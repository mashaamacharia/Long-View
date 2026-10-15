const BASE = import.meta.env.VITE_API_URL ?? "/api";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep status text */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export type StreamHandlers = {
  onEvent: (event: { seq: number; kind: string; node: string | null; title: string; detail: Record<string, unknown> | null; created_at: string | null }) => void;
  onEnd: (state: string) => void;
  onError?: (message: string) => void;
};

/** Follow a run over SSE until the backend sends the terminal `end` event. Returns a closer. */
export function followRun(runId: string, { onEvent, onEnd, onError }: StreamHandlers): () => void {
  const source = new EventSource(`${BASE}/runs/${encodeURIComponent(runId)}/stream?after=0`);
  source.addEventListener("step", (e) => {
    try { onEvent(JSON.parse((e as MessageEvent).data)); } catch { /* skip malformed */ }
  });
  source.addEventListener("end", (e) => {
    try { onEnd(JSON.parse((e as MessageEvent).data).state); } catch { onEnd("unknown"); }
    source.close();
  });
  source.onerror = () => {
    source.close();
    onError?.("The connection to the run stream was lost.");
  };
  return () => source.close();
}
