// Rendered by the Sentry.ErrorBoundary in main.jsx instead of a blank
// white screen when a render error escapes the whole app.
function ErrorFallback() {
  return (
    <div className="dashboard">
      <div className="status-line status-error" style={{ margin: 24 }}>
        Something went wrong loading the dashboard.{" "}
        <button className="back-link" onClick={() => window.location.reload()}>
          Reload the page
        </button>
      </div>
    </div>
  );
}

export default ErrorFallback;
