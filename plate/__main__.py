from argparse import ArgumentParser
import logging
import os
from pathlib import Path
import sys
from threading import Thread
import webbrowser

from . import cli
from .render import stop_plot_processes
from .server import WORKSPACES, make_server


def main():
    if len(sys.argv) > 1 and sys.argv[1] in cli.COMMANDS:
        return cli.main(sys.argv[1:])
    parser = ArgumentParser(
        description="Open Plate in your browser.",
        epilog="For headless use, run build, apply, inspect or export with --help.",
    )
    parser.add_argument("bundle", nargs="?")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--desktop", action="store_true", help="Start the private macOS app backend.")
    parser.add_argument("--workspaces", type=Path, default=WORKSPACES, help="Override the workspace directory.")
    options = parser.parse_args()
    token = os.environ.pop("PLATE_DESKTOP_TOKEN", "") if options.desktop else ""
    if options.desktop and not token:
        parser.error("Start desktop mode from Plate.app.")
    with make_server(options.bundle, options.workspaces.expanduser().resolve(), desktop_token=token) as server:
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
        if options.desktop:
            def stop_when_app_closes():
                sys.stdin.buffer.read()
                stop_plot_processes()
                server.shutdown()
            Thread(target=stop_when_app_closes, name="Plate app lifetime", daemon=True).start()
        elif not options.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    sys.exit(main())
