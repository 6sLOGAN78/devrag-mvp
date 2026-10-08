import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { ErrorState } from "@/components/error-state";
import { SessionSkeleton } from "@/components/session-skeleton";
import { Button } from "@/components/ui/button";
import { useAuthorization } from "@/hooks/use-authorization";
import { useUserInfoRequest } from "@/hooks/use-user-info-request";
import { applyUserLanguage } from "@/i18n";
import { BareLayout } from "@/layouts/bare-layout";
import { purgeSession } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { applyUserColourSchema } from "@/utils/theme";
import { loginRedirect } from "@/utils/safe-next";
import { isSigningOut } from "@/utils/sign-out-intent";

function SessionError({ onRetry, onSignIn }: { onRetry: () => void; onSignIn: () => void }) {
  const { t } = useTranslation();
  return (
    <BareLayout>
      <ErrorState level="h1" heading={t("session.errorHeading")} onAction={onRetry} />
      <Button variant="ghost" className="mt-2" onClick={onSignIn}>
        {t("session.signInAgain")}
      </Button>
    </BareLayout>
  );
}

/** Runs only with a stored token: content renders once the server has confirmed the user (UI-07). */
function SessionRecovery({ path }: { path: string }) {
  const query = useUserInfoRequest();
  const navigate = useNavigate();
  const user = useUserStore((state) => state.user);
  const data = query.data;

  // The server's language and theme are applied once per recovered user, never again when the cached user object is
  // replaced by a later profile save: that would undo an explicit local choice such as "System" (WR-F06, R-120).
  const appliedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!data) return;
    useUserStore.getState().setUser(data);
    if (appliedFor.current === data.id) return;
    appliedFor.current = data.id;
    applyUserLanguage(data.language);
    applyUserColourSchema(data.colorSchema);
  }, [data]);

  if (query.isError && !query.isFetching) {
    // Network or 5xx: the token is kept (a 401 has already purged it and the guard has redirected).
    return (
      <SessionError
        onRetry={() => void query.refetch()}
        onSignIn={() => {
          purgeSession({ toast: false });
          void navigate(loginRedirect(path), { replace: true });
        }}
      />
    );
  }
  if (data && user !== null && user.id === data.id) return <Outlet />;
  return <SessionSkeleton />;
}

/** Layout route for every `auth: "required"` entry. Decides from the stored token and the fetched user, never from a flag. */
export function RequireAuth() {
  const token = useAuthorization();
  const location = useLocation();
  const path = `${location.pathname}${location.search}`;
  if (token === null) return <Navigate to={isSigningOut() ? loginRedirect("/login") : loginRedirect(path)} replace />;
  return <SessionRecovery path={path} />;
}
