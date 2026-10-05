import { Link } from "react-router";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { copy } from "@/constants/copy";
import { useEffect } from "react";

export default function NotFoundPage() {
  useEffect(() => {
    document.title = `${copy.notFound.heading} - ${copy.app.titleSuffix}`;
  }, []);
  return (
    <div className="pt-16">
      <EmptyState
        display={copy.notFound.display}
        heading={copy.notFound.heading}
        body={copy.notFound.body}
        action={
          <Button asChild>
            <Link to="/">{copy.notFound.action}</Link>
          </Button>
        }
      />
    </div>
  );
}
