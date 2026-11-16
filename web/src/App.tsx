import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider, type RouteObject } from "react-router";
import { Layout } from "./components/Layout";
import { SignInCallback } from "./features/account/AuthGate";
import { CALLBACK_PATH } from "./lib/auth";
import { ApiProblem } from "./lib/api";

// Phase 1 builds four screens (spec, "Designed screens"). Each feature folder fills its
// route in its own PR; until then the route shows only its heading.
export const routes: RouteObject[] = [
  { path: CALLBACK_PATH, element: <SignInCallback /> },
  {
    element: <Layout />,
    children: [
      { index: true, lazy: () => import("./features/today/route") },
      { path: "opportunities", lazy: () => import("./features/opportunities/list-route") },
      { path: "opportunities/:id", lazy: () => import("./features/opportunities/detail-route") },
      { path: "applications", lazy: () => import("./features/applications/list-route") },
      { path: "applications/:id", lazy: () => import("./features/applications/detail-route") },
      { path: "profile", lazy: () => import("./features/profile/route") },
    ],
  },
];

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A problem the user must fix (signed out, not found, not allowed) won't pass on retry.
        retry: (count, error) => !(error instanceof ApiProblem && error.status < 500) && count < 2,
      },
    },
  });
}

// The demo is served from a sub-path (GitHub Pages); the app itself from the root.
const router = createBrowserRouter(routes, {
  basename: import.meta.env.BASE_URL.replace(/\/$/, "") || "/",
});
const queryClient = makeQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
