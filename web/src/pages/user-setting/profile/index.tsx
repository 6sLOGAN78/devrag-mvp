import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useUserStore } from "@/stores/user-store";
import { PasswordCard } from "./password-card";
import { ProfileCard } from "./profile-card";

/**
 * Profile page (UI-34): the profile card and the password card. Everything user-supplied
 * renders as text, or as a validated data-URL image through AvatarInitials; nothing is set as raw HTML (T-02-71).
 */
export default function ProfilePage() {
  const { t, i18n } = useTranslation();
  const user = useUserStore((state) => state.user);
  useEffect(() => {
    document.title = t("profile.pageTitle");
  }, [t, i18n.language]);
  return (
    <div data-testid="profile-page" className="flex flex-col gap-6">
      <PageHeader title={t("profile.title")} />
      {user === null ? (
        <Skeleton className="h-64 w-full max-w-md" aria-hidden="true" />
      ) : (
        <>
          <ProfileCard key={user.id} user={user} />
          <PasswordCard key={`password-${user.id}`} />
        </>
      )}
    </div>
  );
}
