import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { buildRoutes } from "@/routes";
import { registerQueryClient } from "@/services/http";

const router = createBrowserRouter(buildRoutes());

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
