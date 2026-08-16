import { certifications, skills } from "../data";
import { SectionLabel } from "./SectionLabel";

export function Skills() {
  return (
    <section id="skills" className="px-6 md:px-16 py-28 max-w-5xl mx-auto">
      <SectionLabel number="03" title="Skills" />

      <div className="grid md:grid-cols-2 gap-x-12 gap-y-8 mb-16">
        {Object.entries(skills).map(([category, items]) => (
          <div key={category}>
            <h3 className="font-display text-xs tracking-[0.15em] uppercase text-text-muted mb-3">
              {category}
            </h3>
            <div className="flex flex-wrap gap-2">
              {items.map((s) => (
                <span
                  key={s}
                  className="font-display text-xs px-3 py-1.5 bg-bg-card border border-border text-text"
                >
                  {s}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div>
        <h3 className="font-display text-xs tracking-[0.15em] uppercase text-text-muted mb-3">
          Certifications
        </h3>
        <ul className="space-y-1.5">
          {certifications.map((c) => (
            <li key={c} className="text-text-dim text-sm flex items-center gap-2">
              <span className="text-accent">·</span>
              {c}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
