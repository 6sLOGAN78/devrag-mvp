import { Navigate } from "react-router";
import { useAuthorization } from "@/hooks/use-authorization";

/** Entry redirect for `/`: decided from the stored token only. A rejected token is purged by the guard at the target. */
export function RootRedirect({ resolve }: { resolve: (session: { signedIn: boolean }) => string }) {
  const signedIn = useAuthorization() !== null;
  return <Navigate to={resolve({ signedIn })} replace />;
}
