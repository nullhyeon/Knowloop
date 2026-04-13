import type { ReactNode } from "react";

import { ConsoleShell } from "@/components/console/console-shell";

export const dynamic = "force-dynamic";

export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return <ConsoleShell>{children}</ConsoleShell>;
}
