# Torch-TensorRT

get bazel from either: (rename downloaded file to `bazel.exe`)
- https://github.com/bazelbuild/bazel/releases
- https://github.com/bazelbuild/bazelisk/releases

get LibTorch for C++ on windows from https://pytorch.org/get-started/locally/ then extract to a location

prepare a fresh python env and install requirements in file `pyproject.toml` then remove `torch` & `tensorrt` from file

need VS console to build
```
set DISTUTILS_USE_SDK=1
pip wheel . --wheel-dir="dist" --verbose --no-build-isolation
```
bazel output folder `bazel-███/` is a symlink from `%USERPROFILE%\_bazel_███\███\execroot\Torch-TensorRT\bazel-███`

*N.B.* save folder `bazel-out/x64_windows-opt/bin/` elsewhere before clear cache with `bazel clean --expunge`

**bazel build successfully but failed to create python wheel (linker error)**
