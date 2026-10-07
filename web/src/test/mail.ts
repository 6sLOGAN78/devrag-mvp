import { waitUntil } from "./wait-until";

/**
 * Reads captured mail back from the Mailpit HTTP API for live tests (plan 02-18). The code is taken from the
 * message text the user would see, never from Valkey or logs. Waiting goes through the shared wait-until helper.
 */
const CODE_RE = /\b\d{6}\b/;

export function mailpitUrl(): string {
  return (process.env.MAILPIT_URL ?? "http://127.0.0.1:8025").replace(/\/+$/, "");
}

interface MailSummary {
  ID: string;
}

interface MailMessage {
  Subject?: string;
  Text?: string;
}

async function firstSummary(recipient: string): Promise<MailSummary | null> {
  try {
    const response = await fetch(`${mailpitUrl()}/api/v1/search?query=${encodeURIComponent(`to:${recipient}`)}&limit=1`);
    if (!response.ok) return null;
    const found = (await response.json()) as { messages?: MailSummary[] | null };
    return found.messages?.[0] ?? null;
  } catch {
    return null;
  }
}

/** The newest message addressed to `recipient`, once it arrives. */
export async function waitForMail(recipient: string, timeout = 30_000): Promise<MailMessage> {
  const summary = await waitUntil(() => firstSummary(recipient), { timeout, interval: 300, describe: `mail for ${recipient}` });
  const response = await fetch(`${mailpitUrl()}/api/v1/message/${summary.ID}`);
  if (!response.ok) throw new Error(`mail catcher returned HTTP ${response.status} for the message`);
  return (await response.json()) as MailMessage;
}

/** The six-digit code in a message body. */
export function extractCode(message: MailMessage): string {
  const match = CODE_RE.exec(message.Text ?? "");
  if (!match) throw new Error(`no 6-digit code in message: ${message.Subject ?? ""}`);
  return match[0];
}

/** Negative check: true when no message for `recipient` appears within the bounded window. */
export async function noMailFor(recipient: string, timeout = 3_000): Promise<boolean> {
  try {
    await waitUntil(() => firstSummary(recipient), { timeout, interval: 300, describe: `unexpected mail for ${recipient}` });
  } catch {
    return true;
  }
  return false;
}

/** Removes the captured messages addressed to `recipient` (and nothing else). */
export async function deleteMailFor(recipient: string): Promise<void> {
  await fetch(`${mailpitUrl()}/api/v1/search?query=${encodeURIComponent(`to:${recipient}`)}`, { method: "DELETE" });
}
