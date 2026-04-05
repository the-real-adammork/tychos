import { useParams, useSearchParams } from "react-router-dom";
import { ParamEditor } from "@/components/parameters/param-editor";

export default function ParamEditPage() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const fromVersionId = searchParams.get("from") || undefined;
  return (
    <div className="space-y-6">
      <ParamEditor id={id!} versionId={fromVersionId} />
    </div>
  );
}
