import type { Session } from "@supabase/supabase-js";

export function accessTokenFromSession(session: Pick<Session, "access_token"> | null): string | null {
  return session?.access_token || null;
}
