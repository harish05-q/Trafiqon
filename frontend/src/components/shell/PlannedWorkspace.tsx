/** Honest placeholder for a workspace that is not built yet: no mock data, no fake controls. */
export function PlannedWorkspace({
  title,
  milestone,
  items,
}: {
  title: string;
  milestone: string;
  items: string[];
}) {
  return (
    <div className="mx-auto max-w-xl px-6 py-10">
      <h1 className="text-base font-semibold">{title}</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        Not implemented yet (planned for {milestone}). Nothing on this page is live.
      </p>
      <h2 className="mt-4 text-xs font-semibold">Planned scope</h2>
      <ul className="text-muted-foreground mt-1 list-disc pl-5 text-sm">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}
