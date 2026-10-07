import { ErrorState } from "@/components/error-state";
import { useTranslation } from "react-i18next";
import { BareLayout } from "@/layouts/bare-layout";

function RenderError() {
  const { t } = useTranslation();
  return (
    <ErrorState
      level="h1"
      heading={t("renderError.heading")}
      body={t("renderError.body")}
      actionLabel={t("renderError.action")}
      onAction={() => window.location.reload()}
    />
  );
}

/** Page-level errorElement: renders inside the route's layout (render and lazy-chunk failures). */
export default function RouteError() {
  return <RenderError />;
}

/** Layout-level errorElement: the shell itself failed, so render inside the Bare layout. */
export function ShellError() {
  return (
    <BareLayout>
      <RenderError />
    </BareLayout>
  );
}
