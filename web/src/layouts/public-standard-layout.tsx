import { useAuthorization } from "@/hooks/use-authorization";
import { BareLayout } from "./bare-layout";
import { StandardLayout } from "./standard-layout";

/** Public routes declared in the standard layout show the app shell only to a signed-in visitor. */
export function PublicStandardLayout() {
  return useAuthorization() === null ? <BareLayout /> : <StandardLayout />;
}
