import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  toast.dismiss();
  localStorage.clear();
});
