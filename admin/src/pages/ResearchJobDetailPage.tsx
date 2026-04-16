import { useParams } from "react-router-dom";

export default function ResearchJobDetailPage() {
  const { id } = useParams();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Research Job #{id}</h1>
      <p className="text-muted-foreground">Loading…</p>
    </div>
  );
}
