import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-11 w-full rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2 text-sm text-on-surface shadow-sm transition-colors placeholder:text-outline focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  );
});
Input.displayName = "Input";

export { Input };
