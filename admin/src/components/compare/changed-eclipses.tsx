import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

interface ChangedEclipse {
  date: string;
  catalogType: string;
  aError: number | null;
  bError: number | null;
  aSep: number | null;
  bSep: number | null;
  errorDelta: number;
}

interface ChangedEclipsesProps {
  changed: ChangedEclipse[];
}

export function ChangedEclipses({ changed }: ChangedEclipsesProps) {
  if (changed.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No eclipses changed between these two versions.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Type</TableHead>
          <TableHead className="text-right">A Error</TableHead>
          <TableHead className="text-right">B Error</TableHead>
          <TableHead>Change</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {changed.map((eclipse, i) => {
          const improved = eclipse.errorDelta < 0;
          return (
            <TableRow key={i}>
              <TableCell className="font-mono text-sm">{eclipse.date}</TableCell>
              <TableCell>{eclipse.catalogType}</TableCell>
              <TableCell className="text-right font-mono text-sm">
                {eclipse.aError != null ? `${eclipse.aError.toFixed(1)}'` : "—"}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {eclipse.bError != null ? `${eclipse.bError.toFixed(1)}'` : "—"}
              </TableCell>
              <TableCell>
                <Badge
                  className={
                    improved
                      ? "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30"
                      : "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30"
                  }
                >
                  {improved ? "improved" : "worsened"}{" "}
                  {Math.abs(eclipse.errorDelta).toFixed(1)}'
                </Badge>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
