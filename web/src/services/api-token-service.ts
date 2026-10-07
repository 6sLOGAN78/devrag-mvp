import { apiTokenPath, apiTokensPath } from "@/constants/api-paths";
import { request } from "./http";

/** One API token as the page needs it. The beta value the API also returns is dropped here: no screen shows it. */
export interface ApiToken {
  token: string;
  /** Unix milliseconds. */
  createTime: number;
}

interface ApiTokenDto {
  token: string;
  beta?: string;
  create_time: number;
}

function toApiToken(dto: ApiTokenDto): ApiToken {
  return { token: dto.token, createTime: dto.create_time };
}

/** Lists the caller's workspace tokens, newest first. Silent: the page renders its own states (a non-owner gets 403). */
export async function listApiTokens(): Promise<ApiToken[]> {
  const rows = await request<ApiTokenDto[]>({ url: apiTokensPath, method: "GET" }, { silent: true });
  return Array.isArray(rows) ? rows.map(toApiToken) : [];
}

/** Creates a token (no input exists). Silent: the page shows a message chosen from the status. */
export async function createApiToken(): Promise<ApiToken> {
  return toApiToken(await request<ApiTokenDto>({ url: apiTokensPath, method: "POST" }, { silent: true }));
}

/** Deletes the given token. Silent: a 404 means it is already gone and is handled by refreshing the list. */
export async function deleteApiToken(token: string): Promise<void> {
  await request<null>({ url: apiTokenPath(token), method: "DELETE" }, { silent: true });
}
