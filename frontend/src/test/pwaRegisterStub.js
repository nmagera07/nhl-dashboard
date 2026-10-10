// Test stand-in for vite-plugin-pwa's virtual module (there's no service
// worker in jsdom). Tests drive it through `pwaState`.
import { useState } from "react";

export const pwaState = { needRefresh: false, updateServiceWorker: () => Promise.resolve() };

export function useRegisterSW() {
  const needRefresh = useState(pwaState.needRefresh);
  return { needRefresh, offlineReady: useState(false), updateServiceWorker: (...args) => pwaState.updateServiceWorker(...args) };
}
