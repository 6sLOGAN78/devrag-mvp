import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { buildRoutes } from "@/routes";
import { registerNavigate, registerQueryClient } from "@/services/http";

const router = createBrowserRouter(buildRoutes());

// A 401 on a request that carried the current token routes to /login client-side, never with a hard reload (UI-04).
registerNavigate({
  navigate: (to) => router.navigate(to, { replace: true }),
  currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
});

export function App() {
  const [client] = useState(() => {
    const created = new QueryClient();
    registerQueryClient(created);
    return created;
  });
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  );
}
