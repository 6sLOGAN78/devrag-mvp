import { z } from "zod";
import type { InstanceView, ProviderView } from "@/services/model-service";
import type { ProviderSpec } from "./providers";

/**
 * Client rules of the provider dialogs (UI-37). They mirror the server, which stays authoritative: a rule that only the
 * server knows (a private address, a rejected key) comes back as an answer and is shown by `errors.ts`. Messages are
 * i18n keys; `FormMessage` translates them.
 */

/** Model ids are bounded at 128 characters, the composite id `model@provider` has to fit the server's column. */
export const MODEL_ID_MAX = 128;
const BASE_URL_MAX = 255;

export type ProviderMode = "setup" | "change";

/** Values of the set up and change dialogs. All text; empty means not entered. Trimming happens on submit. */
export interface ProviderFormValues {
  apiKey: string;
  baseUrl: string;
  apiVersion: string;
  chatModel: string;
  embeddingModel: string;
}

export interface AddModelValues {
  modelId: string;
  type: "chat" | "embedding";
}

const ABSOLUTE_HTTP_URL = /^https?:\/\/\S+$/i;
const OLLAMA_V1 = /\/v1\/*$/i;
const MODEL_ID_FORBIDDEN = /[\s@]/;

/** Characters, not UTF-16 units. */
const length = (value: string): number => Array.from(value).length;

/** Comparison form of an address: trimmed, no trailing slash. The server treats these as the same address too. */
export function normaliseAddress(value: string | null | undefined): string {
  return (value ?? "").trim().replace(/\/+$/, "");
}

/** The message key for a bad base URL, or null when it passes. Full http or https URL, no user name, password or fragment. */
function addressIssue(raw: string, ollama: boolean): string | null {
  const value = raw.trim();
  if (value === "") return "errors.provider.baseUrlRequired";
  if (value.length > BASE_URL_MAX || !ABSOLUTE_HTTP_URL.test(value) || value.includes("#")) return "errors.provider.baseUrlInvalid";
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return "errors.provider.baseUrlInvalid";
  }
  if (url.hostname === "") return "errors.provider.baseUrlInvalid";
  if (url.username !== "" || url.password !== "") return "errors.provider.baseUrlCredentials";
  if (ollama && OLLAMA_V1.test(url.pathname)) return "errors.provider.ollamaV1";
  return null;
}

/** The message key for a bad model id, or null. 1 to 128 characters, no whitespace and no `@` (the composite id separator). */
function modelIdIssue(raw: string): string | null {
  const value = raw.trim();
  if (value === "") return "errors.model.idRequired";
  if (length(value) > MODEL_ID_MAX) return "errors.model.idMax";
  if (MODEL_ID_FORBIDDEN.test(value)) return "errors.model.idInvalid";
  return null;
}

/** The instance the Change dialogs edit: the one named `default`, else the first configured one. */
export function currentInstance(current: ProviderView | undefined): InstanceView | undefined {
  const configured = current?.instances.filter((instance) => instance.configured) ?? [];
  return configured.find((instance) => instance.name === "default") ?? configured[0];
}

/** True when the stored instance holds a key: required providers always do, an optional one when a tail was supplied. */
function holdsKey(spec: ProviderSpec, instance: InstanceView | undefined): boolean {
  if (spec.fields.key === "required") return true;
  if (spec.fields.key === "optional") return (instance?.last4 ?? "") !== "";
  return false;
}

/** Field list of `ProviderFormValues` as a zod object; every field is a string so react-hook-form always has a value. */
const baseShape = z.object({
  apiKey: z.string(),
  baseUrl: z.string(),
  apiVersion: z.string(),
  chatModel: z.string(),
  embeddingModel: z.string(),
});

/**
 * Rules for one provider.
 *
 * - Set up: the address, version and key fields the provider's table row asks for, then at least one model (the error
 *   sits under the second field).
 * - Change: no model field exists (the dialog sends one registered model taken from `current`), the key is required
 *   for providers that need one, and a changed address or API version for a provider that holds a key requires a newly
 *   typed key, because a saved key is never sent to a different address (planner note 3).
 */
export function providerSchema(spec: ProviderSpec, mode: ProviderMode, current?: ProviderView) {
  return baseShape.superRefine((values, ctx) => {
    const issue = (path: keyof ProviderFormValues, message: string) => ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
    const fields = spec.fields;
    if (fields.baseUrl === "required") {
      const message = addressIssue(values.baseUrl, spec.slug === "ollama");
      if (message !== null) issue("baseUrl", message);
    }
    if (fields.apiVersion && values.apiVersion.trim() === "") issue("apiVersion", "errors.provider.apiVersionRequired");

    const key = values.apiKey.trim();
    if (fields.key === "required" && key === "") {
      issue("apiKey", "errors.provider.keyRequired");
    } else if (mode === "change" && key === "" && holdsKey(spec, currentInstance(current))) {
      const stored = currentInstance(current);
      const moved =
        (fields.baseUrl === "required" && normaliseAddress(values.baseUrl) !== normaliseAddress(stored?.baseUrl)) ||
        (fields.apiVersion && values.apiVersion.trim() !== (stored?.apiVersion ?? "").trim());
      if (moved) issue("apiKey", "errors.provider.keyNewAddress");
    }

    if (mode === "setup") {
      const chat = values.chatModel.trim();
      const embedding = values.embeddingModel.trim();
      if (chat !== "") {
        const message = modelIdIssue(chat);
        if (message !== null) issue("chatModel", message);
      }
      if (embedding !== "") {
        const message = modelIdIssue(embedding);
        if (message !== null) issue("embeddingModel", message);
      }
      if (chat === "" && embedding === "") issue("embeddingModel", "errors.provider.modelRequired");
    }
  });
}

export const addModelSchema = z
  .object({
    modelId: z.string(),
    type: z.enum(["chat", "embedding"]),
  })
  .superRefine((values, ctx) => {
    const message = modelIdIssue(values.modelId);
    if (message !== null) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["modelId"], message });
  });
