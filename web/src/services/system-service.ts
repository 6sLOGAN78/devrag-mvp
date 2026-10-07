import { goHealthPath, pythonStatusPath, systemConfigPath } from "@/constants/api-paths";
import type { HealthData, ServiceHealth } from "@/interfaces/health";
import { ApiError, request, requestWithMeta } from "./http";

function isHealthData(value: unknown): value is HealthData {
  return typeof value === "object" && value !== null && "checks" in value && typeof (value as HealthData).checks === "object";
}

async function fetchHealth(path: string): Promise<ServiceHealth> {
  try {
    const { data, source } = await requestWithMeta<HealthData>({ url: path, method: "GET" }, { silent: true });
    return { kind: data.status === "ok" ? "ok" : "degraded", data, source };
  } catch (error) {
    // A 503 carries the dependency list in the envelope data, so a degraded service still renders.
    if (error instanceof ApiError && error.status === 503 && isHealthData(error.data)) {
      return { kind: "degraded", data: error.data, source: undefined };
    }
    throw error;
  }
}

export const fetchGoHealth = (): Promise<ServiceHealth> => fetchHealth(goHealthPath);
export const fetchPythonStatus = (): Promise<ServiceHealth> => fetchHealth(pythonStatusPath);

/** Public, non-secret server settings. Only the registration switch is read (D-01). */
export interface SystemConfig {
  registerEnabled: boolean;
}

/** Anything other than an explicit `true` counts as off, so a malformed answer fails closed. */
export async function getSystemConfig(): Promise<SystemConfig> {
  const data = await request<{ register_enabled?: unknown } | null>({ url: systemConfigPath, method: "GET", anonymous: true }, { silent: true });
  return { registerEnabled: data?.register_enabled === true };
}
