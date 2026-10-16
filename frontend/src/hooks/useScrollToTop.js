import { useEffect } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

// The page scrolls the window, and the router keeps the scroll position when
// the route changes, so going from halfway down a box score to the Scores
// tab landed halfway down Scores. New pages start at the top; Back and
// Forward (POP) are left to the browser, which puts you where you were.
export function useScrollToTop() {
  const { pathname } = useLocation();
  const navigationType = useNavigationType();
  useEffect(() => {
    if (navigationType !== "POP") window.scrollTo(0, 0);
  }, [pathname, navigationType]);
}
