"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RunsTab } from "./RunsTab";
import { SuitesTab } from "./SuitesTab";

export function ExperimentExplorer() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl px-4 py-4">
        <h1 className="text-base font-semibold">Experiment Explorer</h1>
        <p className="text-muted-foreground mb-3 text-xs">
          Persisted results only. Objective values are derived by the shared evaluator; wall times
          are measured on the machine that ran the worker. Built-in scenarios are synthetic.
        </p>
        <Tabs defaultValue="runs">
          <TabsList>
            <TabsTrigger value="runs">Runs</TabsTrigger>
            <TabsTrigger value="suites">Benchmark suites</TabsTrigger>
          </TabsList>
          <TabsContent value="runs" className="mt-3">
            <RunsTab />
          </TabsContent>
          <TabsContent value="suites" className="mt-3">
            <SuitesTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
