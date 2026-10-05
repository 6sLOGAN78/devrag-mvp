import { useEffect, useState } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

type Theme = NonNullable<ToasterProps["theme"]>;

function readTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function Toaster(props: ToasterProps) {
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      visibleToasts={3}
      closeButton
      toastOptions={{
        classNames: {
          toast: "group border border-border bg-card text-card-foreground shadow-lg",
          description: "text-muted-foreground",
        },
      }}
      {...props}
    />
  );
}
