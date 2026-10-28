import { AppShell } from "@/components/shell/AppShell";

export default function WorkspacesLayout({ children }: LayoutProps<"/">) {
  return <AppShell>{children}</AppShell>;
}
