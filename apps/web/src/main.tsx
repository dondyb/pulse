import "@fontsource/plus-jakarta-sans/400.css";
import "@fontsource/plus-jakarta-sans/500.css";
import "@fontsource/plus-jakarta-sans/600.css";
import "@fontsource/plus-jakarta-sans/700.css";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";

import { Layout } from "@/components/Layout";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import CampaignDetailPage from "@/pages/CampaignDetail";
import CampaignFormPage from "@/pages/CampaignForm";
import CampaignsPage from "@/pages/Campaigns";
import ContactsPage from "@/pages/Contacts";
import DashboardPage from "@/pages/Dashboard";
import JobsPage from "@/pages/Jobs";
import NotFoundPage from "@/pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000,
      retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      refetchOnWindowFocus: true,
    },
  },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/campaigns", element: <CampaignsPage /> },
      { path: "/campaigns/new", element: <CampaignFormPage /> },
      { path: "/campaigns/:id", element: <CampaignDetailPage /> },
      { path: "/campaigns/:id/edit", element: <CampaignFormPage /> },
      { path: "/contacts", element: <ContactsPage /> },
      { path: "/jobs", element: <JobsPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
], {
  future: {
    v7_relativeSplatPath: true,
    v7_fetcherPersist: true,
    v7_normalizeFormMethod: true,
    v7_partialHydration: true,
    v7_skipActionErrorRevalidation: true,
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <RouterProvider router={router} future={{ v7_startTransition: true }} />
        <Toaster position="bottom-right" richColors closeButton toastOptions={{ style: { fontFamily: "inherit" } }} />
      </TooltipProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
