import { Hero } from "./components/Hero";
import { FeaturedProject } from "./components/FeaturedProject";
import { ProjectsGrid } from "./components/ProjectsGrid";
import { Skills } from "./components/Skills";
import { Contact } from "./components/Contact";

export default function App() {
  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="grain-overlay" />
      <Hero />
      <FeaturedProject />
      <ProjectsGrid />
      <Skills />
      <Contact />
    </div>
  );
}
