import { cva, type VariantProps } from "class-variance-authority";
import { CircleAlert, Info } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

const alertVariants = cva("flex items-start gap-2 rounded-md border border-l-4 bg-card px-3 py-2 text-sm font-normal text-card-foreground", {
  variants: {
    variant: {
      default: "border-l-destructive",
      info: "border-l-muted-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof alertVariants> {}

/**
 * Form-level message: card surface, 4px stripe, icon plus text (never colour alone).
 * `default` is the destructive error, announced on insertion (`role="alert"`). `info` is a neutral notice with a muted
 * stripe and an Info icon, read politely (`role="status"`).
 */
const Alert = React.forwardRef<HTMLDivElement, AlertProps>(({ className, children, variant, ...props }, ref) => {
  const info = variant === "info";
  const Icon = info ? Info : CircleAlert;
  return (
    <div ref={ref} role={info ? "status" : "alert"} className={cn(alertVariants({ variant }), className)} {...props}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", info ? "text-muted-foreground" : "text-destructive")} aria-hidden="true" />
      <div className="min-w-0 break-words">{children}</div>
    </div>
  );
});
Alert.displayName = "Alert";

export { Alert, alertVariants };
