import { useEffect } from "react";

// Phones: when the keyboard opens, the visible area (the visual viewport)
// shrinks, but a sheet pinned to the bottom of the page doesn't, and iOS
// shifts the page up to keep the text box in view, pushing the top of the
// chat off screen. This keeps the sheet's bottom on the keyboard and its
// height within what's visible, via CSS variables the mobile styles read.
export function keyboardInsets(viewport, layoutHeight) {
  const covered = Math.max(0, layoutHeight - (viewport.offsetTop + viewport.height));
  return { bottom: `${Math.round(covered)}px`, height: `${Math.round(viewport.height)}px` };
}

export function useKeepAboveKeyboard(open, drawerRef) {
  useEffect(() => {
    const viewport = window.visualViewport;
    const drawer = drawerRef.current;
    if (!open || !viewport || !drawer) return undefined;
    const update = () => {
      const { bottom, height } = keyboardInsets(viewport, window.innerHeight);
      drawer.style.setProperty("--chat-keyboard", bottom);
      drawer.style.setProperty("--chat-visible-height", height);
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
    };
  }, [open, drawerRef]);
}
