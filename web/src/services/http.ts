import axios, {
  type AxiosError,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import type { QueryClient } from "@tanstack/react-query";
import { RetCode } from "@/constants/retcode";
import type { Envelope } from "@/interfaces/envelope";
import i18n from "@/i18n";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { loginRedirect } from "@/utils/safe-next";
import { getAuthorization, removeAuthorization } from "@/utils/authorization";
import { isSigningOut } from "@/utils/sign-out-intent";
import { notifyError } from "./notify";

declare module "axios" {
  interface AxiosRequestConfig {
    /** Suppress the error toast for this request. */
    silent?: boolean;
    /** Never attach the stored token (sign in and sign up: a stale token must not ride along or trigger a purge). */
    anonymous?: boolean;
    /** Internal: the token actually attached to this request, or null when none was sent. */
    sentToken?: string | null;
  }
}

const TIMEOUT_MS = 10_000;
const MAX_MESSAGE_LENGTH = 160;
const SESSION_TOAST_ID = "session-expired";

export class ApiError<T = unknown> extends Error {
  readonly code: number;
  readonly status: number;
  readonly requestId?: string;
  readonly data?: T;
  /** Whole seconds from a numeric `Retry-After` header; absent when the header is missing or not a plain number. */
  readonly retryAfter?: number;

  constructor(init: { code: number; message: string; status: number; requestId?: string; data?: T; retryAfter?: number }) {
    super(init.message);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.requestId = init.requestId;
    this.data = init.data;
    this.retryAfter = init.retryAfter;
  }
}

/** Seconds from a `Retry-After` value; only plain non-negative integers count (HTTP dates and junk are ignored). */
export function parseRetryAfter(value: string | undefined): number | undefined {
  if (value === undefined || !/^\d{1,9}$/.test(value.trim())) return undefined;
  return Number(value.trim());
}

function isEnvelope(value: unknown): value is Envelope<unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).code === "number" &&
    "data" in value
  );
}

function headerValue(headers: unknown, name: string): string | undefined {
  if (!headers || typeof (headers as { get?: unknown }).get !== "function") return undefined;
  const value = (headers as { get: (n: string) => unknown }).get(name);
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

/** Server message is shown only when it is a short, non-empty string. */
function safeMessage(message: unknown, fallback: string): string {
  return typeof message === "string" && message.trim().length > 0 && message.length <= MAX_MESSAGE_LENGTH
    ? message
    : fallback;
}

let queryClient: QueryClient | null = null;

export function registerQueryClient(client: QueryClient): void {
  queryClient = client;
}

/** Client-side navigation hooks supplied by the router so a purge never needs a hard reload. */
export interface SessionNavigator {
  navigate: (to: string) => unknown;
  /** Current path plus search, carried into `next` on the sign-in redirect. */
  currentPath: () => string;
}

let sessionNavigator: SessionNavigator | null = null;

export function registerNavigate(value: SessionNavigator | null): void {
  sessionNavigator = value;
}

/** True only when the effective request URL resolves to the page origin. */
export function isSameOrigin(url: string | undefined, baseURL: string | undefined): boolean {
  try {
    const origin = globalThis.location.origin;
    return new URL(url ?? "", new URL(baseURL || "", origin)).origin === origin;
  } catch {
    return false;
  }
}

/** Purge only when the failing request carried a token that is still the current one. */
function shouldPurge(config: AxiosRequestConfig | undefined): boolean {
  const sent = config?.sentToken;
  return typeof sent === "string" && sent.length > 0 && sent === getAuthorization();
}

export interface PurgeOptions {
  /** Show the "Session expired" toast. Sign out and the password-change flow pass false. Default true. */
  toast?: boolean;
  /** Route to /login through the registered navigator. Default true. Sign out navigates itself and passes false. */
  navigate?: boolean;
}

/**
 * A 401 on a request that carried the current token ends the session. While a deliberate sign-out is running, the
 * session is ending anyway: no "Session expired" toast and no `next` redirect (UI-SPEC "no toast on deliberate sign-out").
 */
function purgeAfterUnauthorised(): void {
  if (isSigningOut()) purgeSession({ toast: false, navigate: false });
  else purgeSession();
}

/**
 * Handles a 401 on a request that carried a token. Only the first such answer finds its token still current and
 * purges; the others (in flight at the same time, or sent with a token that is gone or replaced) end silently, so a
 * non-silent request never adds a "Request failed" toast next to "Session expired" (IN-F04). Returns false when the
 * request carried no token, so the caller reports the 401 like any other failure.
 */
function handleUnauthorised(config: AxiosRequestConfig | undefined): boolean {
  const sent = config?.sentToken;
  if (typeof sent !== "string" || sent.length === 0) return false;
  if (shouldPurge(config)) purgeAfterUnauthorised();
  return true;
}

/** Forgets the signed-in identity and everything fetched under it, without touching the stored token. */
export function dropSessionState(): void {
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  queryClient?.clear();
}

/** Drops the token, the user store and the query cache. Callers that did not expire the session pass `toast: false`. */
export function purgeSession(options: PurgeOptions = {}): void {
  removeAuthorization();
  dropSessionState();
  if (options.toast !== false) {
    notifyError({
      id: SESSION_TOAST_ID,
      title: i18n.t("toast.session.title"),
      description: i18n.t("toast.session.description"),
    });
  }
  if (options.navigate !== false && sessionNavigator) void sessionNavigator.navigate(loginRedirect(sessionNavigator.currentPath()));
}

function toastFor(error: ApiError, silent: boolean): void {
  if (silent) return;
  const { status, code, message } = error;
  const id = `${status}:${code}:${message}`;
  if (status === 0) {
    const timedOut = message === i18n.t("toast.timeout.title");
    const scope = timedOut ? "toast.timeout" : "toast.network";
    notifyError({ id, title: i18n.t(`${scope}.title`), description: i18n.t(`${scope}.description`) });
  } else if (status >= 500 && code === -1) {
    notifyError({ id, title: i18n.t("toast.serverError.title"), description: i18n.t("toast.serverError.description") });
  } else {
    notifyError({
      id,
      title: i18n.t("toast.apiError.title"),
      description: safeMessage(message, i18n.t("toast.apiError.fallback")),
      code,
    });
  }
}

export const http = axios.create({ baseURL: "", timeout: TIMEOUT_MS });

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAuthorization();
  if (token && config.anonymous !== true && isSameOrigin(config.url, config.baseURL)) {
    config.headers.set("Authorization", `Bearer ${token}`);
    config.sentToken = token;
  } else {
    config.sentToken = null;
  }
  return config;
});

http.interceptors.response.use(
  (response: AxiosResponse) => {
    const body: unknown = response.data;
    if (!isEnvelope(body)) return response;
    if (body.code === RetCode.SUCCESS) return response;
    const error = new ApiError({
      code: body.code,
      message: typeof body.message === "string" ? body.message : "",
      status: response.status,
      requestId: headerValue(response.headers, "x-request-id"),
      data: body.data,
    });
    if (body.code === RetCode.UNAUTHORIZED && handleUnauthorised(response.config)) {
      /* session ended (or already ended by a concurrent request): no separate toast */
    } else toastFor(error, response.config.silent === true);
    return Promise.reject(error);
  },
  (failure: AxiosError) => {
    if (axios.isCancel(failure)) return Promise.reject(failure);
    const silent = failure.config?.silent === true;
    const response = failure.response;
    let error: ApiError;
    if (!response) {
      const timedOut = failure.code === "ECONNABORTED" || failure.code === "ETIMEDOUT";
      error = new ApiError({
        code: -1,
        status: 0,
        message: timedOut ? i18n.t("toast.timeout.title") : i18n.t("toast.network.title"),
      });
    } else {
      const body: unknown = response.data;
      const envelope = isEnvelope(body) ? body : null;
      error = new ApiError({
        code: envelope ? envelope.code : -1,
        message: envelope && typeof envelope.message === "string" ? envelope.message : "",
        status: response.status,
        requestId: headerValue(response.headers, "x-request-id"),
        data: envelope?.data,
        retryAfter: parseRetryAfter(headerValue(response.headers, "retry-after")),
      });
    }
    if ((error.status === 401 || error.code === RetCode.UNAUTHORIZED) && handleUnauthorised(failure.config)) {
      /* session ended (or already ended by a concurrent request): no separate toast */
    } else toastFor(error, silent);
    return Promise.reject(error);
  },
);

/**
 * Narrows a success body to an object whose `required` keys are non-empty strings. A server that answers success with
 * `data: null`, no `data`, or a record without its identifying field is a protocol fault: it fails with a clear
 * ApiError (status 200, code -1) instead of a TypeError deep inside a mapper (IN-F07).
 */
export function expectRecord<T extends object>(value: unknown, what: string, required: readonly string[]): T {
  const record = typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  const missing = record === null ? required[0] : required.find((key) => typeof record[key] !== "string" || record[key] === "");
  if (record === null || missing !== undefined) {
    throw new ApiError({ code: -1, status: 200, message: `Malformed response from ${what}: expected ${record === null ? "an object" : `a non-empty "${missing}"`}` });
  }
  return record as T;
}

export async function requestWithMeta<T>(
  config: AxiosRequestConfig,
  opts?: { silent?: boolean },
): Promise<{ data: T; source: string | undefined }> {
  const response = await http.request({ ...config, silent: opts?.silent ?? config.silent });
  const body: unknown = response.data;
  const data = (isEnvelope(body) ? body.data : body) as T;
  return { data, source: headerValue(response.headers, "x-api-source") };
}

export async function request<T>(config: AxiosRequestConfig, opts?: { silent?: boolean }): Promise<T> {
  return (await requestWithMeta<T>(config, opts)).data;
}
