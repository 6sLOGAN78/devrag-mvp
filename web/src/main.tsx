import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app";
import "@/i18n";
import { applyTheme, getThemeChoice } from "@/utils/theme";
import "@/index.css";

applyTheme(getThemeChoice());

const root = document.getElementById("root");
if (!root) throw new Error("#root element is missing from index.html");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
