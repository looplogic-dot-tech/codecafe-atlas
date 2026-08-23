# CodeCafe Atlas v1.0.24.25 — Windows build and portable distro

## Normal build

Double-click `build_windows.bat` or run it from PowerShell as `./build_windows.bat`.

The script now performs the entire sequence automatically:

1. Creates or repairs `.venv`.
2. Tries the persistent local cache under `packages/windows-<architecture>/py<version>/` first.
3. If the cache is incomplete and Internet is available, downloads the missing dependency set into that cache.
4. Installs the build environment from the local cache.
5. Runs public-identity, cumulative full-functionality and pre-build validators.
6. Builds with PyInstaller in `%LOCALAPPDATA%/CodeCafeAtlasBuild/1.0.24.25`, outside synchronized source paths.
7. Starts the locally staged `CodeCafe-Atlas.exe` for a real smoke test. A build that immediately fails to start is rejected.
8. Copies the accepted distro to `dist/CodeCafe-Atlas`.
9. Creates `release/CodeCafe_Atlas_v1.0.24.25_Windows_x64.zip`.

## Offline rebuilds

After the package cache has been populated once for the same operating system, architecture and Python major/minor version, the cached files remain under `packages/`. `.venv`, `build`, `dist` and `release` can be deleted and recreated without losing the dependency cache.

To explicitly prove that the cache is complete without allowing Internet access:

`py bootstrap_dependencies.py --offline`

## Windows runtime/path issue addressed in this release

v1.0.24.23 produced a valid executable, but during testing a build located in a synchronized OneDrive source path temporarily failed while loading `python314.dll`; the identical distro started correctly from a normal local path. v1.0.24.25 therefore performs PyInstaller output and the first executable startup test in a local `%LOCALAPPDATA%` staging directory before accepting the build.

The generated portable ZIP should be extracted before execution. For the most predictable runtime behavior, use a normal local folder rather than running the extracted application from a folder that is actively synchronized or virtualized by a cloud client.
