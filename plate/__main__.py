from argparse import ArgumentParser
import logging
import webbrowser

from .server import make_server


def main():
    parser = ArgumentParser(description="Open Plate in your browser.")
    parser.add_argument("bundle", nargs="?")
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()
    with make_server(options.bundle) as server:
        logging.basicConfig(filename=server.session.workspace / "plate.log", level=logging.INFO)
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
