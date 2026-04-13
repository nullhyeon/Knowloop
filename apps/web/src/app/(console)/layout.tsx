import type { ReactNode } from "react";

import { ContextBootstrapProvider } from "@/components/console/context-bootstrap-provider";
import { ConsoleShell } from "@/components/console/console-shell";

export const dynamic = "force-dynamic";

export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <ContextBootstrapProvider>
      <ConsoleShell>{children}</ConsoleShell>
    </ContextBootstrapProvider>
  );
}
