"use client";

import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";

import { cn } from "@/lib/utils";

const Label = React.forwardRef(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(
      "font-label text-xs font-medium uppercase tracking-[0.02em] text-on-surface-variant",
      className,
    )}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
