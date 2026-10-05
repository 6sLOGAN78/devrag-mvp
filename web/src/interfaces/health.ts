import type { components, paths } from "./openapi";

export type ProbeResult = components["schemas"]["ProbeResult"];
/** Python health payload, generated from the exported OpenAPI. */
export type PythonHealthData = components["schemas"]["HealthData"];

export type DependencyName = "database" | "redis" | "storage" | "doc_store";

/** Go reports only database and redis; the shape is otherwise identical. */
export interface HealthData {
  status: string;
  engine: string;
  checks: Partial<Record<DependencyName, ProbeResult>>;
}

/** `degraded` is any dependency down (HTTP 503 with the dependency list in the envelope). */
export interface ServiceHealth {
  kind: "ok" | "degraded";
  data: HealthData;
  source: string | undefined;
}

export const dependencyOrder: readonly DependencyName[] = ["database", "redis", "storage", "doc_store"];

/** The 200 body of the Python healthz route, straight from the exported OpenAPI (API-08). */
export type PythonHealthzResponse = paths["/api/v1/system/healthz"]["get"]["responses"]["200"]["content"]["application/json"];

/** Compile-time check that the generated envelope carries the hand-written HealthData shape. */
export const asHealthData = (body: PythonHealthzResponse): HealthData => body.data;
