import { useRegisterSW } from "virtual:pwa-register/react";

const CHECK_EVERY_MS = 60 * 60 * 1000;

// "A new version is ready": when a new release has downloaded in the
// background, offer to switch to it instead of waiting for the next launch.
// (With automatic updates, an installed app kept showing the old version
// until it was closed and reopened -- sometimes twice.)
function UpdateBanner() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    // Check hourly too, so a tab or installed app left open all evening
    // still hears about a release.
    onRegisteredSW(_url, registration) {
      if (registration) setInterval(() => registration.update().catch(() => {}), CHECK_EVERY_MS);
    },
  });

  if (!needRefresh) return null;
  return (
    <div className="update-banner" role="status">
      <span>🏒 A new version of PuckPulse is ready.</span>
      <button type="button" className="update-banner-refresh" onClick={() => updateServiceWorker(true)}>Refresh</button>
      <button type="button" className="update-banner-dismiss" aria-label="Dismiss" onClick={() => setNeedRefresh(false)}>✕</button>
    </div>
  );
}

export default UpdateBanner;
