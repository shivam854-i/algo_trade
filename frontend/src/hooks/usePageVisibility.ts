import { useEffect, useState } from "react";

/**
 * Hook that tracks browser tab visibility via the Page Visibility API.
 * Returns `true` when the tab is active/visible, and `false` when hidden or minimized.
 * Enables pausing background polling, chart rendering, and network tasks to eliminate
 * browser memory bloat and background CPU/battery drain.
 */
export function usePageVisibility(): boolean {
  const [isVisible, setIsVisible] = useState<boolean>(() => {
    if (typeof document !== "undefined") {
      return !document.hidden;
    }
    return true;
  });

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return isVisible;
}
