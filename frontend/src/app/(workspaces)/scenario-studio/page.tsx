import { PlannedWorkspace } from "@/components/shell/PlannedWorkspace";

export default function ScenarioStudioPage() {
  return (
    <PlannedWorkspace
      title="Scenario Studio"
      milestone="M6"
      items={[
        "Create and edit nodes and directed roads",
        "Road costs and closures, depots, customers and demands, fleet",
        "Connectivity and feasibility validation",
        "Save as a new immutable version",
      ]}
    />
  );
}
