/** User-facing strings (01-UI-SPEC.md Copywriting Contract). */
export const copy = {
  app: {
    wordmark: "devRag",
    titleSuffix: "devRag",
  },
  nav: {
    systemStatus: "System status",
    groupCaption: "Platform",
    openMenu: "Open navigation menu",
    closeMenu: "Close",
  },
  a11y: {
    skipLink: "Skip to main content",
    primaryNav: "Primary",
  },
  theme: {
    label: "Change theme",
    light: "Light",
    dark: "Dark",
    system: "System",
  },
  notFound: {
    display: "404",
    heading: "Page not found",
    body: "This page doesn't exist or isn't available in this version. Go back to System status.",
    action: "Go to System status",
  },
  errorState: {
    headingFor: (noun: string) => `Couldn't load ${noun}`,
    body: "The request failed. Check your connection and try again. If it keeps failing, check System status.",
    action: "Try again",
    codeLabel: "Code",
  },
  renderError: {
    heading: "Something went wrong",
    body: "This page failed to load. Reload to try again.",
    action: "Reload page",
  },
  emptyState: {
    fallbackHeading: "Nothing here yet",
    headingFor: (noun: string) => `No ${noun} yet`,
  },
  status: {
    title: "System status",
    pageTitle: "System status - devRag",
    refresh: "Refresh status",
    loading: "Checking services",
    updated: (time: string) => `Updated ${time}`,
    sourceLabel: "X-API-Source",
    healthy: "Healthy",
    degraded: "Degraded",
    unreachable: "Unreachable",
    down: "Down",
    ok: "OK",
    goApi: "Go API",
    pythonApi: "Python API",
    errorNoun: "service status",
    dependencies: {
      database: "Database",
      redis: "Redis",
      storage: "Storage",
      doc_store: "Doc store",
    },
  },
  toast: {
    apiError: {
      title: "Request failed",
      fallback: "The server rejected the request. Try again.",
    },
    serverError: {
      title: "Server error",
      description: "The server hit a problem. Try again in a moment.",
    },
    network: {
      title: "Can't reach the server",
      description: "Check your connection and try again.",
    },
    timeout: {
      title: "Request timed out",
      description: "The server took too long to respond. Try again.",
    },
    session: {
      title: "Session expired",
      description: "Your session ended. Reload the page to continue.",
    },
  },
} as const;
