import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const PARAM_FIELDS = [
  "orbit_radius",
  "orbit_center_a",
  "orbit_center_b",
  "orbit_center_c",
  "orbit_tilt_a",
  "orbit_tilt_b",
  "start_pos",
  "speed",
] as const;

type ParamField = (typeof PARAM_FIELDS)[number];

const BODY_GROUPS = [
  { label: "Earth & Polar Axis", bodies: ["earth", "polar_axis"] },
  { label: "Sun", bodies: ["sun_def", "sun"] },
  { label: "Moon", bodies: ["moon_def_a", "moon_def_b", "moon"] },
  { label: "Mercury", bodies: ["mercury_def_a", "mercury_def_b", "mercury"] },
  { label: "Venus", bodies: ["venus_def_a", "venus_def_b", "venus"] },
  { label: "Mars", bodies: ["mars_def_e", "mars_def_s", "mars", "phobos", "deimos"] },
  {
    label: "Outer Planets",
    bodies: [
      "jupiter_def", "jupiter",
      "saturn_def", "saturn",
      "uranus_def", "uranus",
      "neptune_def", "neptune",
    ],
  },
  {
    label: "Comets & Asteroids",
    bodies: ["halleys_def", "halleys", "eros_def_a", "eros_def_b", "eros"],
  },
];

type BodyParams = Partial<Record<ParamField, number | string>>;
type ParamsData = Record<string, BodyParams>;

function formatVal(val: number | string | undefined): string {
  if (val == null || val === "") return "—";
  if (typeof val === "number") {
    // Strip trailing zeros but keep precision
    return Number(val.toPrecision(10)).toString();
  }
  return String(val);
}

interface ParamViewerProps {
  paramsJson: string;
}

export function ParamViewer({ paramsJson }: ParamViewerProps) {
  let params: ParamsData;
  try {
    params = JSON.parse(paramsJson) as ParamsData;
  } catch {
    return <p className="text-sm text-destructive">Failed to parse parameters JSON</p>;
  }

  return (
    <div className="space-y-4">
      {BODY_GROUPS.map((group) => {
        const bodiesInGroup = group.bodies.filter((b) => params[b]);
        if (bodiesInGroup.length === 0) return null;
        return (
          <Card key={group.label}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{group.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="text-left pb-1 pr-3 font-normal">Body</th>
                      {PARAM_FIELDS.map((f) => (
                        <th key={f} className="text-right pb-1 px-2 font-normal">
                          {f.replace("orbit_", "").replace("_", " ")}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {bodiesInGroup.map((body) => (
                      <tr key={body} className="border-b border-border/50 last:border-0">
                        <td className="py-1 pr-3 text-foreground">{body}</td>
                        {PARAM_FIELDS.map((f) => (
                          <td key={f} className="py-1 px-2 text-right tabular-nums">
                            {formatVal(params[body]?.[f])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
