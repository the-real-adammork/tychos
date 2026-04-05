import * as React from "react";
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
  aDetected: boolean;
  bDetected: boolean;
  aSep: number | null;
  bSep: number | null;
}

interface ChangedEclipsesProps {
  changed: ChangedEclipse[];
}

export function ChangedEclipses({ changed }: ChangedEclipsesProps) {
  if (changed.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No eclipses changed detection status between these two versions.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Type</TableHead>
          <TableHead className="text-right">A Sep (arcmin)</TableHead>
          <TableHead className="text-right">B Sep (arcmin)</TableHead>
          <TableHead>Change</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {changed.map((eclipse, i) => {
          const isNewDetect = !eclipse.aDetected && eclipse.bDetected;
          const isLost = eclipse.aDetected && !eclipse.bDetected;
          return (
            <TableRow key={i}>
              <TableCell className="font-mono text-sm">{eclipse.date}</TableCell>
              <TableCell>{eclipse.catalogType}</TableCell>
              <TableCell className="text-right font-mono text-sm">
                {eclipse.aSep != null ? eclipse.aSep.toFixed(2) : "—"}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {eclipse.bSep != null ? eclipse.bSep.toFixed(2) : "—"}
              </TableCell>
              <TableCell>
                {isNewDetect && (
                  <Badge className="bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30">
                    NEW DETECT
                  </Badge>
                )}
                {isLost && (
                  <Badge variant="destructive">
                    LOST
                  </Badge>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
