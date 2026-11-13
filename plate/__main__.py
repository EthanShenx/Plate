from argparse import ArgumentParser
import logging
from pathlib import Path
import webbrowser

from .server import WORKSPACES, make_server


def main():
    parser = ArgumentParser(description="Open Plate in your browser.")
    parser.add_argument("bundle", nargs="?")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--workspaces", type=Path, default=WORKSPACES, help="Override the workspace directory.")
    options = parser.parse_args()
    with make_server(options.bundle, options.workspaces.expanduser().resolve()) as server:
        class WorkspaceLog(logging.Handler):
            def emit(self, record):
                try:
                    with (server.session.workspace / "plate.log").open("a", encoding="utf-8") as stream:
                        stream.write(self.format(record) + "\n")
                except OSError:
                    self.handleError(record)

        logging.basicConfig(level=logging.INFO, handlers=[WorkspaceLog()])
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"Plate is running at {url}", flush=True)
        if not options.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
