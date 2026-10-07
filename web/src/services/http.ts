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
import { getAuthorization, removeAuthorization } from "@/utils/authorization";
import { notifyError } from "./notify";

declare module "axios" {
  interface AxiosRequestConfig {
    /** Suppress the error toast for this request. */
    silent?: boolean;
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

  constructor(init: { code: number; message: string; status: number; requestId?: string; data?: T }) {
    super(init.message);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.requestId = init.requestId;
    this.data = init.data;
  }
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

/** True only when the effective request URL resolves to the page origin. */
export function isSameOrigin(url: string | undefined, baseURL: string | undefined): boolean {
  try {
    const origin = window.location.origin;
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

function purgeSession(): void {
  removeAuthorization();
  useUserStore.getState().reset();
  queryClient?.clear();
  notifyError({
    id: SESSION_TOAST_ID,
    title: i18n.t("toast.session.title"),
    description: i18n.t("toast.session.description"),
  });
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
  if (token && isSameOrigin(config.url, config.baseURL)) {
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
    if (body.code === RetCode.UNAUTHORIZED && shouldPurge(response.config)) purgeSession();
    else toastFor(error, response.config.silent === true);
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
      });
    }
    if ((error.status === 401 || error.code === RetCode.UNAUTHORIZED) && shouldPurge(failure.config)) purgeSession();
    else toastFor(error, silent);
    return Promise.reject(error);
  },
);

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
