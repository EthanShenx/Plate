import { useState } from "react";
import { createRoot } from "react-dom/client";

const shortDate = new Intl.DateTimeFormat(undefined, {
  day: "numeric", month: "short", year: "numeric",
});

function Icon({ name }) {
  return <svg className="icon" aria-hidden="true"><use href={`./icons.svg#${name}`} /></svg>;
}

function FigureRow({ figure, onOpen }) {
  return (
    <li>
      <button type="button" className="project-columns project-row" onClick={() => onOpen(figure.id)}>
        <span className="project-identity">
          <Icon name="figure" />
          <span className="project-name">{figure.name}</span>
        </span>
        <span className="project-source" title={figure.bundle || undefined}>{figure.bundle.split("/").at(-1) || "Local draft"}</span>
        <time dateTime={new Date(figure.modified * 1000).toISOString()}>{shortDate.format(figure.modified * 1000)}</time>
        <Icon name="arrow" />
      </button>
    </li>
  );
}

function Projects({ projects, onOpen }) {
  const [query, setQuery] = useState("");
  const term = query.trim().toLocaleLowerCase();
  const results = projects.filter(project =>
    project.name.toLocaleLowerCase().includes(term) || project.figures.some(figure =>
      figure.name.toLocaleLowerCase().includes(term) || figure.bundle.toLocaleLowerCase().includes(term)));
  return (
    <>
      <div className="project-filters">
        <label className="project-search">
          <Icon name="search" />
          <input type="search" aria-label="Search projects and figures" placeholder="Search projects and figures"
            value={query} onChange={event => setQuery(event.target.value)} />
        </label>
      </div>
      {results.length ? (
        <ul className="project-list">
          {results.map(project => (
            <li key={project.id}>
              <details open>
                <summary className="project-summary">
                  <span>{project.name}</span>
                  <span className="project-caption">{project.figures.length} {project.figures.length === 1 ? "figure" : "figures"}</span>
                </summary>
                <ul className="project-list project-figures-list">
                  {project.figures.map(figure => <FigureRow key={figure.id} figure={figure} onOpen={onOpen} />)}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <div className="project-empty">
          <Icon name={term ? "search" : "figure"} />
          <h2>{term ? "No matching projects or figures" : "No projects here yet"}</h2>
          <p>{term ? "Try a different name." : "Create a project or open a .plate file to get started."}</p>
        </div>
      )}
    </>
  );
}

export function mountProjects(container, onOpen) {
  const root = createRoot(container);
  return projects => root.render(<Projects projects={projects} onOpen={onOpen} />);
}
