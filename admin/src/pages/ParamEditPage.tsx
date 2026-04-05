import { useParams } from "react-router-dom";
import { ParamEditor } from "@/components/parameters/param-editor";

export default function ParamEditPage() {
  const { id } = useParams();
  return (
    <div className="space-y-6">
      <ParamEditor id={id!} />
    </div>
  );
}
