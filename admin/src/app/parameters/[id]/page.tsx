import { ParamEditor } from "@/components/parameters/param-editor";

export default async function ParamDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="space-y-6">
      <ParamEditor id={id} />
    </div>
  );
}
