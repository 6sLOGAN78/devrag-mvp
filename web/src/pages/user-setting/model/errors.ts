import axios from "axios";
import i18n from "@/i18n";
import { ApiError } from "@/services/http";

/**
 * How a failed provider call is worded (UI-SPEC checker flags 2 and 3, Pitfall 7).
 *
 * The server answers by HTTP status and a machine `data.reason`; this module turns that pair into one i18n key. Only a
 * provider refusal carries server text (bounded to 300 characters, rendered as a text node by the caller); every other
 * answer has fixed copy. Nothing here produces the words session, sign in or unauthorized: a refused key is not an
 * authentication event, and a real 401 ends the session in the shared interceptor before any dialog gets to word it.
 */
export interface ProviderFailure {
  /** Locale key of the message. For a refusal this is the fallback sentence used when `text` is absent. */
  key: string;
  /** The provider's own reason, for a refusal only. */
  text?: string;
  /** Set when the answer belongs under the key field instead of in the alert. */
  field?: "key";
  /** True for a provider refusal: the alert gets the "{provider} refused this configuration" title. */
  refusal: boolean;
}

const MAX_REFUSAL_TEXT = 300;
const GENERIC = "models.refused.generic";

function reasonOf(error: ApiError): string {
  const data = error.data;
  if (typeof data !== "object" || data === null) return "";
  const reason = (data as Record<string, unknown>).reason;
  return typeof reason === "string" ? reason : "";
}

const plain = (key: string, field?: "key"): ProviderFailure => (field === undefined ? { key, refusal: false } : { key, field, refusal: false });

function fromNetwork(timedOut: boolean): ProviderFailure {
  return plain(timedOut ? "models.timeout" : "models.providerDown");
}

/** True for a request the dialog itself cancelled (Esc, Close, unmount). Not a failure to report. */
export function isAborted(error: unknown): boolean {
  return axios.isCancel(error);
}

/** The classification of a failed set up, change key, change address or add model call. */
export function providerErrorKey(error: unknown): ProviderFailure {
  if (axios.isAxiosError(error)) return fromNetwork(error.code === "ECONNABORTED" || error.code === "ETIMEDOUT");
  if (!(error instanceof ApiError)) return plain(GENERIC);
  const { status } = error;
  const reason = reasonOf(error);
  if (status === 0) return fromNetwork(error.message === i18n.t("toast.timeout.title"));
  if (status === 400) {
    if (reason === "provider_refused") {
      const text = error.message.trim();
      return text !== "" && text.length <= MAX_REFUSAL_TEXT ? { key: "models.refused.fallback", text, refusal: true } : { key: "models.refused.fallback", refusal: true };
    }
    if (reason === "key_required_for_new_address") return plain("errors.provider.keyNewAddress", "key");
    if (reason === "key_required") return plain("errors.provider.keyRequired", "key");
    if (reason === "base_url_refused") return plain("models.error.addressRefused");
    if (reason === "dimension_mismatch" || reason === "dimension_unsupported") return plain("models.error.dimension");
    return plain(GENERIC);
  }
  if (status === 409 && reason === "model_exists") return plain("models.error.modelExists");
  if (status === 429) return plain("models.rateLimited");
  if (status === 503) return plain(reason === "provider_rate_limited" ? "models.providerBusy" : "models.keyStoreDown");
  if (status === 504) return plain("models.timeout");
  if (status === 502) return plain("models.providerDown");
  if (status === 403) return plain("workspace.forbidden");
  return plain(GENERIC);
}

/** Message key for a failed delete: a lost permission is said so, everything else is "nothing was removed". */
export function deleteFailureKey(error?: unknown): string {
  return error instanceof ApiError && error.status === 403 ? "workspace.forbidden" : "models.delete.failed";
}
