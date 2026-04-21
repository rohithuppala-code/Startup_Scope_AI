import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

let _client: SupabaseClient | null = null;

export const supabase: SupabaseClient = (() => {
  // During SSR build, env vars may not be present — return a dummy-safe client
  if (!supabaseUrl || !supabaseAnonKey) {
    // Return a proxy that won't crash during build but will work at runtime
    if (typeof window === "undefined") {
      return new Proxy({} as SupabaseClient, {
        get: () => () => ({ data: null, error: null }),
      });
    }
  }
  if (!_client) {
    _client = createClient(supabaseUrl, supabaseAnonKey);
  }
  return _client;
})();

