import { PlannedWorkspace } from "@/components/shell/PlannedWorkspace";

export default function AlgorithmLabPage() {
  return (
    <PlannedWorkspace
      title="Algorithm Lab"
      milestone="M6"
      items={[
        "Full parameter configuration with descriptions",
        "Seed and stopping budget",
        "Convergence chart from stored run history",
        "Execution statistics and algorithm diagnostics",
      ]}
    />
  );
}
