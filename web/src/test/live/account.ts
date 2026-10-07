/**
 * Registers a real account through the live ingress and returns its access token (plan 02-14).
 *
 * The Python status and catch-all routes need a signed-in caller, so live tests sign in through the real
 * Go endpoints (`POST /api/v1/users`, `POST /api/v1/auth/login`); nothing is faked. The throwaway password
 * and e-mail are obviously fake and unique per call. The rows are not removed from here (no database access
 * from the browser tier); the Python and Go tiers own account cleanup.
 */
const TEST_PASSWORD = "test-only-pass-0001";

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(new URL(path, window.location.origin), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  const envelope = (await response.json()) as Envelope<T>;
  if (envelope.code !== 0) throw new Error(`${path} returned envelope code ${envelope.code}`);
  return envelope.data;
}

export async function registerLiveAccount(prefix = "web"): Promise<string> {
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  const email = `${prefix}-${suffix}@example.test`;
  await post("/api/v1/users", { email, password: TEST_PASSWORD, nickname: `${prefix}-${suffix}` });
  const login = await post<{ token: string }>("/api/v1/auth/login", { email, password: TEST_PASSWORD });
  if (!login.token) throw new Error("login returned no token");
  return login.token;
}
