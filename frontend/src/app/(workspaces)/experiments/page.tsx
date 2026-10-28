import { PlannedWorkspace } from "@/components/shell/PlannedWorkspace";

export default function ExperimentsPage() {
  return (
    <PlannedWorkspace
      title="Experiment Explorer"
      milestone="M6"
      items={[
        "Run and benchmark-suite history with filters",
        "Side-by-side comparison from stored results",
        "Seed-level inspection and reproducibility metadata",
        "CSV and JSON export",
      ]}
    />
  );
}
