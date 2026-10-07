import * as React from "react";
import { cn } from "@/lib/utils";

/** Plain semantic table (UI-SPEC: no Radix primitive). The wrapper scrolls horizontally on narrow screens. */
const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(({ className, ...props }, ref) => (
  <div className="w-full overflow-x-auto">
    <table ref={ref} className={cn("w-full caption-top text-sm", className)} {...props} />
  </div>
));
Table.displayName = "Table";

const TableCaption = React.forwardRef<HTMLTableCaptionElement, React.HTMLAttributes<HTMLTableCaptionElement>>(
  ({ className, ...props }, ref) => <caption ref={ref} className={cn("sr-only", className)} {...props} />,
);
TableCaption.displayName = "TableCaption";

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <thead ref={ref} className={cn("bg-muted", className)} {...props} />,
);
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <tbody ref={ref} className={className} {...props} />,
);
TableBody.displayName = "TableBody";

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(({ className, ...props }, ref) => (
  <tr ref={ref} className={cn("h-12 border-b last:border-b-0", className)} {...props} />
));
TableRow.displayName = "TableRow";

/** Column header: always `scope="col"`, Label size at weight 600. */
const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, scope = "col", ...props }, ref) => (
    <th ref={ref} scope={scope} className={cn("h-10 px-4 text-left text-xs font-semibold text-muted-foreground", className)} {...props} />
  ),
);
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(({ className, ...props }, ref) => (
  <td ref={ref} className={cn("px-4 py-2 align-middle", className)} {...props} />
));
TableCell.displayName = "TableCell";

export { Table, TableCaption, TableHeader, TableBody, TableRow, TableHead, TableCell };
