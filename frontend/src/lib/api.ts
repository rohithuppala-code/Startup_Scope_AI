const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface FetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

export async function api<T = unknown>(
  path: string,
  opts: FetchOptions & { userId?: string } = {}
): Promise<T> {
  const { userId, body, headers: extraHeaders, ...rest } = opts;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(extraHeaders as Record<string, string>),
  };
  
  if (typeof window !== "undefined") {
    try {
      const stateStr = localStorage.getItem("startupscope-user");
      if (stateStr) {
        const state = JSON.parse(stateStr);
        if (state?.state?.accessToken) {
          headers["Authorization"] = `Bearer ${state.state.accessToken}`;
        }
      }
    } catch (e) {}
  }
  
  if (userId) headers["x-user-id"] = userId;

  const res = await fetch(`${BASE}${path}`, {
    ...rest,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}
