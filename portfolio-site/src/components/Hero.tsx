import { profile } from "../data";

// PHOTO SLOT: drop a professional photo at public/portrait.jpg and flip
// this to true. A tasteful, small, duotone-treated photo genuinely adds
// value here — recruiters connect a face to a name faster, and it
// humanizes what's otherwise a very technical page. Kept small and
// framed like an ID badge rather than a big glamour headshot, to stay
// consistent with the "engineering log" aesthetic. Falls back to a
// monogram badge if no photo is set, so the layout never breaks.
const HAS_PHOTO = true;

export function Hero() {
  return (
    <header className="relative min-h-screen flex flex-col justify-center px-6 md:px-16 overflow-hidden">
      {/* faint scanline / grid backdrop for depth */}
      <div
        className="absolute inset-0 opacity-[0.07] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-border-strong) 1px, transparent 1px), linear-gradient(90deg, var(--color-border-strong) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />

      <div className="relative max-w-5xl mx-auto w-full grid md:grid-cols-[1fr_auto] gap-12 items-center">
        <div className="animate-fade-up">
          <div className="font-display text-xs tracking-[0.3em] uppercase text-accent mb-6">
            {profile.location} · available for hire
          </div>

          <h1 className="font-display font-extrabold text-[clamp(2.5rem,7vw,5rem)] leading-[0.95] tracking-tight mb-6">
            {profile.name}
          </h1>

          <p className="font-display text-xl md:text-2xl text-accent mb-6">
            {profile.title}
          </p>

          <p className="max-w-xl text-text-dim text-lg leading-relaxed mb-10">
            {profile.subtitle}
          </p>

          <div className="flex flex-wrap gap-4 font-display text-sm">
            <a
              href="#featured"
              className="px-5 py-3 bg-accent text-bg font-semibold hover:bg-accent-bright transition-colors"
            >
              View AI SDR →
            </a>
            <a
              href={profile.resumeFile}
              download
              className="px-5 py-3 border border-border-strong hover:border-accent transition-colors"
            >
              ↓ Resume
            </a>
            <a
              href={profile.github}
              target="_blank"
              rel="noreferrer"
              className="px-5 py-3 border border-border-strong hover:border-accent transition-colors"
            >
              GitHub
            </a>
            <a
              href={profile.linkedin}
              target="_blank"
              rel="noreferrer"
              className="px-5 py-3 border border-border-strong hover:border-accent transition-colors"
            >
              LinkedIn
            </a>
          </div>
        </div>

        <div className="animate-fade-up hidden md:flex flex-col items-center gap-3" style={{ animationDelay: "0.15s" }}>
          <div className="bracket-corners w-40 h-40 flex items-center justify-center bg-bg-card border border-border overflow-hidden">
            {HAS_PHOTO ? (
              <img
                src="/portrait.jpg"
                alt={profile.name}
                className="w-full h-full object-cover"
                style={{ filter: "grayscale(0.3) contrast(1.05)" }}
              />
            ) : (
              <span className="font-display text-4xl text-accent-dim">PS</span>
            )}
          </div>
          <span className="font-display text-[10px] tracking-[0.2em] uppercase text-text-muted">
            id · 2026
          </span>
        </div>
      </div>

      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 font-display text-[10px] tracking-[0.3em] uppercase text-text-muted animate-fade-up" style={{ animationDelay: "0.3s" }}>
        scroll ↓
      </div>
    </header>
  );
}
