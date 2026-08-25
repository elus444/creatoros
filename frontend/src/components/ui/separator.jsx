"use client";

import * as SeparatorPrimitive from "@radix-ui/react-separator";

import { cn } from "@/lib/utils";

function Separator({ className, orientation = "horizontal", decorative = true, ...props }) {
  return (
    <SeparatorPrimitive.Root
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-outline-variant",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
