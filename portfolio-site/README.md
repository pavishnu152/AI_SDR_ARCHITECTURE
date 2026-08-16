# Pavishnu S — Portfolio

Single-page portfolio site. React + TypeScript + Tailwind CSS v4, built with
Vite. Content lives in [`src/data.ts`](src/data.ts) — update it there, not in
the components, to change any copy, project details, or links.

## Local development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build   # outputs to dist/
npm run preview # serve the production build locally
```

## Deploying to Vercel

This folder lives inside the `AI-SDR-Architecture` repo rather than its own
— when connecting it on Vercel:

1. [vercel.com/new](https://vercel.com/new), import the `AI-SDR-Architecture`
   GitHub repo.
2. In the project's **Root Directory** setting, set it to `portfolio-site`
   (not the repo root) — this is what tells Vercel to treat this subfolder
   as its own deployable app.
3. Framework preset: Vercel auto-detects Vite. Build command
   `npm run build`, output directory `dist` — should be filled in
   automatically.
4. Deploy. No environment variables needed — this site has no backend, it's
   fully static.

Once deployed, update `demoUrl` and `githubUrl` in
[`src/data.ts`](../portfolio-site/src/data.ts) with the live AI SDR demo
link and GitHub repo link once those exist, then redeploy.

## Structure

```
src/
├── data.ts              # all content — edit here first
├── App.tsx               # assembles the page
├── components/
│   ├── Hero.tsx            # name, pitch, links, photo
│   ├── FeaturedProject.tsx # AI SDR deep-dive
│   ├── ProjectsGrid.tsx    # other 4 projects from the resume
│   ├── Skills.tsx          # categorized skills + certifications
│   ├── Contact.tsx         # email, links, resume download
│   └── SectionLabel.tsx    # numbered section header, reused everywhere
public/
├── portrait.jpg           # professional photo, used in the hero
├── Pavishnu_Resume.pdf    # downloadable resume
└── ai-sdr-architecture.svg # copied from the AI SDR project's docs/
```
