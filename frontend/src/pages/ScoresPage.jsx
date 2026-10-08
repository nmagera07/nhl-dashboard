import Scoreboard from "../components/Scoreboard.jsx";

function ScoresPage() {
  const today = new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
  return (
    <main className="page">
      <div className="page-header">
        <h1>Scores</h1>
        <span className="page-subtitle">{today}</span>
      </div>
      <Scoreboard />
    </main>
  );
}

export default ScoresPage;
