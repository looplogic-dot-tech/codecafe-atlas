# Atlas offline package cache

This directory is intentionally persistent.

`bootstrap_dependencies.py` stores downloaded Python distributions here by operating system, CPU architecture and Python major/minor version, for example:

`packages/windows-x86_64/py314/`

The first build on a new platform/Python combination may require Internet access if the matching cache is empty or incomplete. After the required distributions are cached, Atlas installs the build environment from this folder with `pip --no-index --find-links`, so repeated builds do not need to download the same packages again.

`.venv`, `build`, `dist` and `release` are disposable build artifacts. `packages` is the reusable dependency store.
