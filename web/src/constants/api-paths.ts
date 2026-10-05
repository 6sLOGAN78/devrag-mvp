import routeTable from "./api-routes.generated.json";

interface GeneratedRoute {
  owner: "go" | "python";
  match: "exact" | "prefix";
  path: string;
}

/** Looks a path up in the generated route table (from conf/routes.yaml); a miss is a build-time bug. */
function resolve(owner: GeneratedRoute["owner"], path: string): string {
  const found = (routeTable.routes as GeneratedRoute[]).find((r) => r.owner === owner && r.match === "exact" && r.path === path);
  if (!found) throw new Error(`route ${path} (${owner}) is not in api-routes.generated.json`);
  return found.path;
}

// The lookup keys below are the registry entries; components import only the resolved constants.
export const goHealthPath = resolve("go", "/health");
export const pythonStatusPath = resolve("python", "/api/v1/system/status");
