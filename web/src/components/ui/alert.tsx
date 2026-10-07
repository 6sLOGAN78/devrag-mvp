import { CircleAlert } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

/** Form-level error: card surface, 4px destructive stripe, icon plus text (never colour alone). Announced on insertion. */
const Alert = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    role="alert"
    className={cn("flex items-start gap-2 rounded-md border border-l-4 border-l-destructive bg-card px-3 py-2 text-sm font-normal text-card-foreground", className)}
    {...props}
  >
    <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
    <div className="min-w-0 break-words">{children}</div>
  </div>
));
Alert.displayName = "Alert";

export { Alert };
