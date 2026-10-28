import * as React from "react";

import { cn } from "@/lib/utils";

/** Native <select> styled with the design tokens: accessible and keyboard-friendly by default. */
export function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "border-input bg-secondary text-foreground h-8 w-full min-w-0 rounded-md border px-2 text-sm",
        "focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
