import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach } from "vitest";
import i18n from "@/i18n";

beforeEach(async () => {
  // Phase 1 tests assert exact English text, so every test starts in English.
  localStorage.clear();
  await i18n.changeLanguage("en");
  document.documentElement.lang = "en";
});

afterEach(() => {
  cleanup();
  toast.dismiss();
  localStorage.clear();
});
