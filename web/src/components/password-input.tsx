import { Eye, EyeOff } from "lucide-react";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Input, type InputProps } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface PasswordInputProps extends Omit<InputProps, "type"> {
  /** Changing this value hides the password again (the form bumps it after a failed submit). */
  resetSignal?: number;
}

/**
 * Password field with a show/hide button. It hides again on unmount (state is local) and on `resetSignal`.
 * Pointer activation keeps focus and caret in the input; keyboard users stay on the button.
 */
const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(function PasswordInput({ className, resetSignal, ...props }, ref) {
  const { t } = useTranslation();
  const showLabel = t("auth.password.show");
  const hideLabel = t("auth.password.hide");
  const [revealed, setRevealed] = React.useState(false);
  React.useEffect(() => {
    setRevealed(false);
  }, [resetSignal]);
  return (
    <div className="relative">
      <Input ref={ref} type={revealed ? "text" : "password"} className={cn("pr-10", className)} {...props} />
      <button
        type="button"
        data-testid="password-toggle"
        aria-pressed={revealed}
        aria-label={revealed ? hideLabel : showLabel}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => setRevealed((value) => !value)}
        className="absolute right-0 top-0 inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:w-11"
      >
        {revealed ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
      </button>
    </div>
  );
});

export { PasswordInput };
