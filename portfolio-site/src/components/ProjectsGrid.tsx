import { otherProjects } from "../data";
import { SectionLabel } from "./SectionLabel";

export function ProjectsGrid() {
  return (
    <section id="projects" className="px-6 md:px-16 py-28 max-w-5xl mx-auto">
      <SectionLabel number="02" title="Other Projects" />

      <div className="grid md:grid-cols-2 gap-px bg-border">
        {otherProjects.map((proj) => (
          <a
            key={proj.name}
            href={proj.githubUrl}
            target="_blank"
            rel="noreferrer"
            className="group bg-bg p-8 hover:bg-bg-card transition-colors"
          >
            <div className="flex items-start justify-between gap-4 mb-3">
              <h3 className="font-display text-lg font-semibold leading-snug">{proj.name}</h3>
              <span className="font-display text-xs text-text-muted group-hover:text-accent transition-colors shrink-0">
                ↗
              </span>
            </div>
            <div className="font-display text-sm text-accent mb-4">{proj.metric}</div>
            <p className="text-text-dim text-[0.92rem] leading-relaxed mb-5">{proj.description}</p>
            <div className="flex flex-wrap gap-2">
              {proj.stack.map((s) => (
                <span key={s} className="font-display text-[11px] px-2 py-1 border border-border text-text-muted">
                  {s}
                </span>
              ))}
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}
