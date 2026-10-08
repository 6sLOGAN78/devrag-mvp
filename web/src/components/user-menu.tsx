import { LogOut, UserRound } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { AvatarInitials } from "@/components/avatar-initials";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { purgeSession } from "@/services/http";
import { logout } from "@/services/user-service";
import { useUserStore } from "@/stores/user-store";
import { beginSignOut, endSignOut } from "@/utils/sign-out-intent";

/**
 * Account menu for the signed-in shell. Nickname, email and avatar are user-supplied and render as text or as a
 * validated data-URL image only.
 */
export function UserMenu() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useUserStore((state) => state.user);
  const signingOut = useRef(false);
  if (user === null) return null;

  const signOut = async () => {
    if (signingOut.current) return;
    signingOut.current = true;
    // Mark the intent before the request: logout answers 401 for an expired token, and that must not read as an expiry.
    beginSignOut();
    try {
      await logout();
    } catch {
      // A failed request must never leave a usable local session (T-02-53B): fall through to the local purge.
    } finally {
      // Deliberate sign out lands on a bare /login: the guard must not add the expiry-style `next` parameter.
      purgeSession({ toast: false, navigate: false });
      try {
        await navigate("/login", { replace: true });
      } finally {
        endSignOut();
        signingOut.current = false;
      }
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("header.accountMenu")} data-testid="user-menu">
          <AvatarInitials avatar={user.avatar} nickname={user.nickname} email={user.email} size="sm" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="flex flex-col gap-0.5 font-normal">
          <span className="truncate text-sm font-semibold">{user.nickname}</span>
          <span className="truncate text-xs font-normal text-muted-foreground">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/user-setting/profile" data-testid="user-menu-profile">
            <UserRound aria-hidden="true" />
            {t("nav.profile")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="user-menu-signout" onSelect={() => void signOut()}>
          <LogOut aria-hidden="true" />
          {t("header.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
