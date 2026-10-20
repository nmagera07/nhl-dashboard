import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { titleFor } from "../seo/site.js";

// Sets document.title from the current route (see seo/site.js titleFor).
export default function usePageTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = titleFor(pathname);
  }, [pathname]);
}
