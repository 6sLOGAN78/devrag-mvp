import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import type { ApiToken } from "@/services/api-token-service";
import { copyToken } from "./clipboard";
import { DeleteTokenDialog } from "./delete-dialog";
import { maskToken, tokenTail } from "./mask";

/** How long the copy button shows the check mark. */
export const COPIED_MS = 2000;

function createdLabel(createTime: number, language: string): { iso: string; text: string } | null {
  const date = new Date(createTime);
  if (!Number.isFinite(createTime) || Number.isNaN(date.getTime())) return null;
  return { iso: date.toISOString(), text: new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(date) };
}

/**
 * One token row. Reveal state is local to the row, so leaving the page forgets it. The accessible names carry the
 * token tail only. Copy always writes the full value; if copying fails the token is revealed so it can be selected.
 */
export function TokenRow({ token, onDeleted }: { token: ApiToken; onDeleted: () => void }) {
  const { t, i18n } = useTranslation();
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null);
  const tail = tokenTail(token.token);
  const created = createdLabel(token.createTime, i18n.language);

  useEffect(
    () => () => {
      if (timer.current !== null) globalThis.clearTimeout(timer.current);
    },
    [],
  );

  async function copy(): Promise<void> {
    const ok = await copyToken(token.token);
    if (!ok) {
      setRevealed(true);
      return;
    }
    setCopied(true);
    if (timer.current !== null) globalThis.clearTimeout(timer.current);
    timer.current = globalThis.setTimeout(() => setCopied(false), COPIED_MS);
  }

  const iconButton = "text-muted-foreground hover:text-foreground";
  return (
    <TableRow data-testid="token-row">
      <TableCell className="font-mono text-sm">
        <span data-testid="token-value" className={revealed ? "break-all" : "whitespace-nowrap"}>
          {revealed ? token.token : maskToken(token.token)}
        </span>
      </TableCell>
      <TableCell className="whitespace-nowrap">
        {created === null ? "-" : <time dateTime={created.iso}>{created.text}</time>}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            data-testid="token-reveal"
            aria-pressed={revealed}
            aria-label={revealed ? t("tokens.action.hide", { last4: tail }) : t("tokens.action.show", { last4: tail })}
            className={iconButton}
            onClick={() => setRevealed((value) => !value)}
          >
            {revealed ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            data-testid="token-copy"
            data-copied={copied}
            aria-label={t("tokens.action.copy", { last4: tail })}
            className={iconButton}
            onClick={() => void copy()}
          >
            {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          </Button>
          <DeleteTokenDialog token={token.token} onDeleted={onDeleted} />
        </div>
      </TableCell>
    </TableRow>
  );
}
