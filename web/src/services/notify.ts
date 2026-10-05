import { createElement, type ReactNode } from "react";
import { toast } from "sonner";

const ERROR_DURATION_MS = 8000;
const SUCCESS_DURATION_MS = 4000;

export interface NotifyErrorOptions {
  title: string;
  description: string;
  code?: number;
  /** Dedupe key: identical ids update the visible toast instead of stacking. */
  id: string;
}

function body(description: string, code?: number): ReactNode {
  return createElement(
    "span",
    null,
    createElement("span", null, description),
    code === undefined ? null : createElement("span", { className: "mt-1 block font-mono text-xs" }, `Code ${code}`),
  );
}

export function notifyError({ title, description, code, id }: NotifyErrorOptions): void {
  toast.error(title, {
    id,
    description: body(description, code),
    duration: ERROR_DURATION_MS,
    closeButton: true,
  });
}

export function notifySuccess(title: string, description?: string): void {
  toast.success(title, { description, duration: SUCCESS_DURATION_MS, closeButton: true });
}
