workspace(name = "Torch-TensorRT")

load("//tools/cpp:cc_configure.bzl", "cc_configure")

cc_configure()

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

http_archive(
    name = "rules_python",
    sha256 = "863ba0fa944319f7e3d695711427d9ad80ba92c6edd0b7c7443b84e904689539",
    strip_prefix = "rules_python-0.22.0",
    url = "https://github.com/bazelbuild/rules_python/releases/download/0.22.0/rules_python-0.22.0.tar.gz",
)

load("@rules_python//python:repositories.bzl", "py_repositories")

py_repositories()

http_archive(
    name = "rules_pkg",
    sha256 = "8f9ee2dc10c1ae514ee599a8b42ed99fa262b757058f65ad3c384289ff70c4b8",
    urls = [
        "https://mirror.bazel.build/github.com/bazelbuild/rules_pkg/releases/download/0.9.1/rules_pkg-0.9.1.tar.gz",
        "https://github.com/bazelbuild/rules_pkg/releases/download/0.9.1/rules_pkg-0.9.1.tar.gz",
    ],
)

load("@rules_pkg//:deps.bzl", "rules_pkg_dependencies")

rules_pkg_dependencies()

http_archive(
    name = "googletest",
    sha256 = "755f9a39bc7205f5a0c428e920ddad092c33c8a1b46997def3f1d4a82aded6e1",
    strip_prefix = "googletest-5ab508a01f9eb089207ee87fd547d290da39d015",
    urls = ["https://github.com/google/googletest/archive/5ab508a01f9eb089207ee87fd547d290da39d015.zip"],
)

####################################################################################
# Locally installed dependencies (use in cases of custom dependencies or aarch64)
####################################################################################

new_local_repository(
    name = "libtorch",
    build_file = "third_party/libtorch/BUILD",
    path = "<path to libtorch extracted>",
)

new_local_repository(
    name = "libtorch_pre_cxx11_abi",
    build_file = "third_party/libtorch/BUILD",
    path = "<path to libtorch extracted>",
)

new_local_repository(
    name = "cuda",
    build_file = "@//third_party/cuda:BUILD",
    path = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v1█.█",
)

new_local_repository(
    name = "cublas",
    build_file = "@//third_party/cublas:BUILD",
    path = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v1█.█",
)

new_local_repository(
    name = "cudnn",
    build_file = "@//third_party/cudnn/local:BUILD",
    path = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v1█.█",
)

new_local_repository(
    name = "tensorrt",
    build_file = "@//third_party/tensorrt/local:BUILD",
    path = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v1█.█",
)

#########################################################################
# Development Dependencies (optional - comment out on aarch64)
#########################################################################

load("@rules_python//python:pip.bzl", "pip_parse")

pip_parse(
    name = "devtools_deps",
    requirements = "//:requirements-dev.txt",
)

load("@devtools_deps//:requirements.bzl", "install_deps")

install_deps()
