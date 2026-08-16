import { featuredProject as p } from "../data";
import { SectionLabel } from "./SectionLabel";

export function FeaturedProject() {
  return (
    <section id="featured" className="px-6 md:px-16 py-28 max-w-5xl mx-auto">
      <SectionLabel number="01" title="Featured Project" />

      <div className="grid md:grid-cols-[1.3fr_1fr] gap-12">
        <div>
          <h3 className="font-display text-3xl md:text-4xl font-bold mb-3">{p.name}</h3>
          <p className="text-accent font-display text-sm mb-6">{p.tagline}</p>
          <p className="text-text-dim leading-relaxed mb-8">{p.description}</p>

          <div className="flex flex-wrap gap-2 mb-10">
            {p.stack.map((s) => (
              <span
                key={s}
                className="font-display text-xs px-3 py-1 border border-border text-text-dim"
              >
                {s}
              </span>
            ))}
          </div>

          <div className="flex flex-wrap gap-4 font-display text-sm mb-10">
            {p.demoUrl ? (
              <a
                href={p.demoUrl}
                target="_blank"
                rel="noreferrer"
                className="px-5 py-3 bg-accent text-bg font-semibold hover:bg-accent-bright transition-colors"
              >
                Live demo →
              </a>
            ) : (
              <span className="px-5 py-3 border border-border-strong text-text-muted cursor-not-allowed">
                Live demo (deploying)
              </span>
            )}
            {p.githubUrl ? (
              <a
                href={p.githubUrl}
                target="_blank"
                rel="noreferrer"
                className="px-5 py-3 border border-border-strong hover:border-accent transition-colors"
              >
                Source →
              </a>
            ) : (
              <span className="px-5 py-3 border border-border-strong text-text-muted cursor-not-allowed">
                Source (pending push)
              </span>
            )}
          </div>

          <div className="space-y-5">
            {p.highlights.map((h) => (
              <div key={h.label} className="border-l-2 border-accent-dim pl-4">
                <div className="font-display text-sm text-accent mb-1">{h.label}</div>
                <div className="text-text-dim text-[0.95rem] leading-relaxed">{h.detail}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div className="bracket-corners bg-bg-card border border-border p-2">
            <img
              src={p.diagramSrc}
              alt="AI SDR architecture diagram"
              className="w-full h-auto"
              loading="lazy"
            />
          </div>

          <div className="grid grid-cols-2 gap-px bg-border">
            {p.stats.map((s) => (
              <div key={s.label} className="bg-bg-card p-5">
                <div className="font-display text-2xl text-accent mb-1">{s.value}</div>
                <div className="text-xs text-text-muted leading-snug">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
