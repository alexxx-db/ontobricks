import ItemsPanel from "../features/items/ItemsPanel";
import SignedInAs from "../features/me/SignedInAs";

export default function App() {
  return (
    <main>
      <p className="eyebrow">React + FastAPI + Lakebase</p>
      <h1>Lakebase web app</h1>
      <p className="intro">A minimal full-stack Databricks App template.</p>
      <SignedInAs />
      <ItemsPanel />
    </main>
  );
}
