import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  const { t, i18n } = useTranslation();
  useEffect(() => {
    document.title = t("notFound.pageTitle");
  }, [t, i18n.language]);
  return (
    <div className="pt-16">
      <EmptyState
        display={t("notFound.display")}
        heading={t("notFound.heading")}
        body={t("notFound.body")}
        action={
          <Button asChild>
            <Link to="/">{t("notFound.action")}</Link>
          </Button>
        }
      />
    </div>
  );
}
