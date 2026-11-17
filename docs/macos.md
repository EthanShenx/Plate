# Plate for macOS

Run `make macos` using the checkout’s Python and Node prerequisites and the macOS command-line tools. The build creates `output/Plate.app`, ad-hoc signed for local use on the build Mac. Run `open output/Plate.app` or double-click it in Finder. Set `MAC_APP=/path/to/Plate.app` to change the build destination. The binary and packaged Python extensions match the architecture and Python minor version used at build time.

If the checkout is under a synced Desktop or Documents folder, build directly into your user Applications folder to keep Finder metadata from changing the app bundle. Quit Plate first, then run `make macos MAC_APP="$HOME/Applications/Plate.app"`.

The Swift AppKit shell hosts the existing web interface in WKWebView and starts a private copy of the loopback Python backend. The app uses a per-launch, HTTP-only cookie and a nonpersistent WebKit store. It accepts navigation only on its own loopback origin. The native bridge exposes a fixed set of file pickers. Plate has no accounts or remote sessions. Project files and scripts run with the current user’s permissions.

Window placement and appearance live in macOS preferences. The desktop workspace library and backend log live in `~/Library/Application Support/Plate/Desktop`. The desktop automatically resumes a recent workspace. Use **File → Open** or double-click a `.plate` file to open a project. Save a bundle to move a draft between the desktop and browser workspace libraries. Avoid saving over the same bundle from two live sessions.

## Troubleshooting

- For a script that fails to render, open **Edit script → More → Check dependencies** to check the interpreter and see the package install command.
- If R reports a missing Cairo PDF device, install [XQuartz](https://www.xquartz.org/) and restart Plate.
- If you import SVG artwork, install librsvg with `brew install librsvg`.

## Test on the Mac

Run `make test-macos` in a signed-in macOS GUI session and `make test` for the shared backend suite. The native smoke test launches a separate copy of the app with a temporary workspace. It checks the loopback session, native file sheets, R/Python rendering, an editable PDF export, appearance settings, window reopening, and polling when hidden.

For a longer exercise, run:

```sh
.venv/bin/python desktop/test.py --soak-seconds 7200
```

For WebKit heap snapshots, quit Plate, run `defaults write org.platesci.Plate PlateWebInspector -bool true`, then reopen it. Choose its workspace in Safari’s **Develop** menu and take JavaScript allocation snapshots in the **Timelines** tab before and after repeatedly opening the script editor and switching projects. Use Instruments **Allocations** or **Activity Monitor** alongside it to inspect native memory and energy use. Remove the inspector preference with `defaults delete org.platesci.Plate PlateWebInspector` after testing.

The visible workspace checks for script and input changes about once a second. Polling pauses while the window is closed, minimized, or hidden and resumes when it becomes visible or the Mac wakes. Layout undo retains up to 50 changes. Plot output is spooled to temporary files and Plate keeps the last 64 KiB from each output stream.
