import { useLocation } from "react-router";
import { SessionRecovery } from "@/components/require-auth";
import { useAuthorization } from "@/hooks/use-authorization";
import { BareLayout } from "./bare-layout";
import { StandardLayout } from "./standard-layout";

/**
 * Public routes declared in the standard layout (Not Found) show the app shell only to a signed-in visitor, and only
 * once the session is confirmed: the user menu, sign out and revoked-token detection need the recovered user (WR-F05).
 * A signed-out visitor stays in the bare layout and no session request is made, so the route is never guarded.
 */
export function PublicStandardLayout() {
  const token = useAuthorization();
  const location = useLocation();
  if (token === null) return <BareLayout />;
  return (
    <SessionRecovery path={`${location.pathname}${location.search}`}>
      <StandardLayout />
    </SessionRecovery>
  );
}
