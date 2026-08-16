interface Props {
  number: string;
  title: string;
}

export function SectionLabel({ number, title }: Props) {
  return (
    <div className="flex items-center gap-3 mb-10">
      <span className="font-display text-sm text-accent tabular-nums">{number}</span>
      <span className="h-px flex-1 max-w-8 bg-border-strong" />
      <h2 className="font-display text-xs tracking-[0.25em] uppercase text-text-dim">
        {title}
      </h2>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
