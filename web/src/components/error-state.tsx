import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { copy } from "@/constants/copy";

interface ErrorStateProps {
  heading?: string;
  noun?: string;
  body?: string;
  actionLabel?: string;
  onAction?: () => void;
  code?: string | number;
  /** Heading level: page-level errors use h1, in-card errors use h3. */
  level?: "h1" | "h3";
}

export function ErrorState({ heading, noun, body, actionLabel, onAction, code, level = "h3" }: ErrorStateProps) {
  const Heading = level;
  const title = heading ?? copy.errorState.headingFor(noun ?? "data");
  return (
    <div data-testid="error-state" role="alert" className="flex flex-col items-start gap-2">
      <AlertTriangle className="size-6 text-destructive" aria-hidden="true" />
      <Heading className="text-xl font-semibold leading-tight">{title}</Heading>
      <p className="text-sm text-muted-foreground">{body ?? copy.errorState.body}</p>
      {code !== undefined ? (
        <p className="font-mono text-xs text-muted-foreground">
          {copy.errorState.codeLabel} {code}
        </p>
      ) : null}
      {onAction ? (
        <Button onClick={onAction} className="mt-2">
          {actionLabel ?? copy.errorState.action}
        </Button>
      ) : null}
    </div>
  );
}
