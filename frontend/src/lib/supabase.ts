import { createClient, SupabaseClient } from "@supabase/supabase-js";

let _client: SupabaseClient | null = null;

/**
 * Lazily creates and caches the Supabase client.
 * Calling this at module-eval time (before env vars are injected by Next.js)
 * was crashing with "supabaseUrl is required".
 *
 * We defer construction until first use, which is always after Next.js has
 * injected NEXT_PUBLIC_* env vars into the browser bundle.
 */
function getClient(): SupabaseClient {
  if (_client) return _client;

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

  if (!supabaseUrl || !supabaseAnonKey) {
    // Return a no-op proxy during SSR/build so imports don't crash.
    // At runtime in the browser, env vars are always available after Next.js hydration.
    return new Proxy({} as SupabaseClient, {
      get: (_, prop) => {
        if (prop === "from") return () => ({ select: () => ({ eq: () => ({ data: null, error: null }) }) });
        if (prop === "channel") return () => ({ on: () => ({ subscribe: () => ({}) }), unsubscribe: () => {} });
        if (prop === "realtime") return { setAuth: () => {} };
        return () => Promise.resolve({ data: null, error: null });
      },
    });
  }

  _client = createClient(supabaseUrl, supabaseAnonKey, {
    realtime: {
      params: { eventsPerSecond: 10 },
    },
  });
  return _client;
}

/**
 * The Supabase browser client — access via this proxy so it's always lazy.
 *
 * Usage: `supabase.from("posts").select("*")` etc.
 */
export const supabase = new Proxy({} as SupabaseClient, {
  get(_, prop: string) {
    return (getClient() as unknown as Record<string, unknown>)[prop];
  },
});
