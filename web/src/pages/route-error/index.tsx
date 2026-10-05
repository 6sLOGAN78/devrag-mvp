import { ErrorState } from "@/components/error-state";
import { copy } from "@/constants/copy";
import { BareLayout } from "@/layouts/bare-layout";

function RenderError() {
  return (
    <ErrorState
      level="h1"
      heading={copy.renderError.heading}
      body={copy.renderError.body}
      actionLabel={copy.renderError.action}
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
