import { cn } from "@/lib/utils";

// Only raster data URLs render in an <img>. SVG, remote URLs and every other scheme fall back to initials.
const AVATAR_DATA_URL = /^data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/]+={0,2}$/;

/** The avatar value when it is a safe raster data URL, else null. */
export function avatarDataUrl(value: string | null | undefined): string | null {
  return typeof value === "string" && AVATAR_DATA_URL.test(value) ? value : null;
}

/** Up to two initials from the first letters of the first two words of the nickname, else the email's first letter. */
export function initialsOf(nickname: string, email: string): string {
  const nameWords = nickname.trim().split(/\s+/).filter(Boolean);
  const words = nameWords.length > 0 ? nameWords : email.trim().split(/\s+/).filter(Boolean);
  const letters = words.slice(0, 2).map((word) => Array.from(word)[0] ?? "").join("");
  return letters === "" ? "?" : letters.toLocaleUpperCase();
}

const SIZES = { sm: "size-8 text-xs", md: "size-10 text-sm", lg: "size-16 text-xl" } as const;

interface AvatarInitialsProps {
  avatar: string;
  nickname: string;
  email: string;
  size?: keyof typeof SIZES;
  className?: string;
}

/** Decorative: the person's name is always rendered as text next to it, so it is hidden from assistive tech. */
export function AvatarInitials({ avatar, nickname, email, size = "sm", className }: AvatarInitialsProps) {
  const src = avatarDataUrl(avatar);
  return (
    <span
      aria-hidden="true"
      data-testid="avatar-initials"
      className={cn("inline-flex shrink-0 select-none items-center justify-center overflow-hidden rounded-full bg-muted font-semibold text-foreground", SIZES[size], className)}
    >
      {src ? <img src={src} alt="" className="size-full object-cover" /> : initialsOf(nickname, email)}
    </span>
  );
}
