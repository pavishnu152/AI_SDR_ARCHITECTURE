import { profile } from "../data";
import { SectionLabel } from "./SectionLabel";

export function Contact() {
  return (
    <section id="contact" className="px-6 md:px-16 py-28 max-w-5xl mx-auto">
      <SectionLabel number="04" title="Contact" />

      <div className="grid md:grid-cols-[1.3fr_1fr] gap-12 items-start">
        <div>
          <p className="text-2xl md:text-3xl leading-snug mb-8 max-w-lg">
            Open to AI/ML Engineer and Software Engineer roles in Bangalore —
            happy to talk about anything in this page in more depth.
          </p>
          <a
            href={`mailto:${profile.email}`}
            className="font-display text-lg text-accent hover:text-accent-bright transition-colors underline underline-offset-4"
          >
            {profile.email}
          </a>
        </div>

        <div className="font-display text-sm space-y-3">
          <a href={profile.github} target="_blank" rel="noreferrer" className="flex items-center justify-between border-b border-border py-3 hover:text-accent transition-colors">
            GitHub <span>↗</span>
          </a>
          <a href={profile.linkedin} target="_blank" rel="noreferrer" className="flex items-center justify-between border-b border-border py-3 hover:text-accent transition-colors">
            LinkedIn <span>↗</span>
          </a>
          <a href={profile.resumeFile} download className="flex items-center justify-between border-b border-border py-3 hover:text-accent transition-colors">
            Resume (PDF) <span>↓</span>
          </a>
          <a href={`tel:${profile.phone}`} className="flex items-center justify-between border-b border-border py-3 hover:text-accent transition-colors">
            {profile.phone} <span>↗</span>
          </a>
        </div>
      </div>

      <footer className="mt-24 pt-8 border-t border-border font-display text-xs text-text-muted flex flex-col md:flex-row justify-between gap-2">
        <span>{profile.name} — built with React, TypeScript, Tailwind</span>
        <span>© 2026</span>
      </footer>
    </section>
  );
}
