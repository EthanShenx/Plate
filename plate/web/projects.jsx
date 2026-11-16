import { useState } from "react";
import { createRoot } from "react-dom/client";
import { TabsIndicator, TabsList, TabsPanel, TabsRoot, TabsTab } from "./smoothui";

const filters = [
  { id: "all", label: "All projects", matches: () => true },
  { id: "files", label: "Linked files", matches: project => Boolean(project.bundle) },
  { id: "drafts", label: "Drafts", matches: project => !project.bundle },
];
const shortDate = new Intl.DateTimeFormat(undefined, {
  day: "numeric", month: "short", year: "numeric",
});

function Icon({ name }) {
  return <svg className="icon" aria-hidden="true"><use href={`./icons.svg#${name}`} /></svg>;
}

function ProjectList({ projects, query, onOpen }) {
  if (!projects.length) {
    return (
      <div className="project-empty">
        <Icon name={query ? "search" : "figure"} />
        <h2>{query ? "No matching projects" : "No projects here yet"}</h2>
        <p>{query ? "Try a different project name or filename." : "Create a project or open a .plate file to get started."}</p>
      </div>
    );
  }
  return (
    <>
      <div className="project-columns project-column-head" aria-hidden="true">
        <span>Project</span><span>Source</span><span>Last opened or edited</span><span />
      </div>
      <ul className="project-list">
        {projects.map(project => (
          <li key={project.id}>
            <button type="button" className="project-columns project-row" onClick={() => onOpen(project.id)}>
              <span className="project-identity">
                <Icon name="figure" />
                <span>
                  <span className="project-name">{project.name}</span>
                  <span className="project-caption">{project.panels} {project.panels === 1 ? "panel" : "panels"}</span>
                </span>
              </span>
              <span className="project-source" title={project.bundle || undefined}>{project.bundle.split("/").at(-1) || "Local draft"}</span>
              <time dateTime={new Date(project.modified * 1000).toISOString()}>{shortDate.format(project.modified * 1000)}</time>
              <Icon name="arrow" />
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function Projects({ projects, onOpen }) {
  const [query, setQuery] = useState("");
  const term = query.trim().toLocaleLowerCase();
  const results = projects.filter(project =>
    project.name.toLocaleLowerCase().includes(term) ||
    project.bundle.split("/").at(-1).toLocaleLowerCase().includes(term));
  return (
    <TabsRoot className="project-tabs" defaultValue="all">
      <div className="project-filters">
        <TabsList aria-label="Filter projects" activateOnFocus>
          {filters.map(({ id, label }) => <TabsTab key={id} value={id}>{label}</TabsTab>)}
          <TabsIndicator />
        </TabsList>
        <label className="project-search">
          <Icon name="search" />
          <input type="search" aria-label="Search projects" placeholder="Search projects"
            value={query} onChange={event => setQuery(event.target.value)} />
        </label>
      </div>
      {filters.map(({ id, matches }) => (
        <TabsPanel key={id} value={id}>
          <ProjectList projects={results.filter(matches)} query={term} onOpen={onOpen} />
        </TabsPanel>
      ))}
    </TabsRoot>
  );
}

export function mountProjects(container, onOpen) {
  const root = createRoot(container);
  return projects => root.render(<Projects projects={projects} onOpen={onOpen} />);
}
