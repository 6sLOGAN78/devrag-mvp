/** User-facing strings (01-UI-SPEC.md Copywriting Contract). Plan 01-12 adds page copy. */
export const copy = {
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
