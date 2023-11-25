import glob
import os
import platform
import re
import subprocess
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from distutils.cmd import Command
from pathlib import Path
from shutil import copyfile, rmtree
from typing import List

import setuptools
import yaml
from setuptools import Extension, find_namespace_packages, setup
from setuptools.command.build_ext import build_ext
from setuptools.command.develop import develop
from setuptools.command.editable_wheel import editable_wheel
from setuptools.command.install import install
from torch.utils import cpp_extension
from wheel.bdist_wheel import bdist_wheel

__version__: str = "0.0.0"
__cuda_version__: str = "0.0"
__cudnn_version__: str = "0.0"
__tensorrt_version__: str = "0.0"

LEGACY_BASE_VERSION_SUFFIX_PATTERN = re.compile("a0$")


def get_root_dir() -> Path:
    return Path(
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
        .decode("ascii")
        .strip()
    )


def get_git_revision_short_hash() -> str:
    return (
        subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
        .decode("ascii")
        .strip()
    )


def get_base_version() -> str:
    root = get_root_dir()
    try:
        dirty_version = open(root / "version.txt", "r").read().strip()
    except FileNotFoundError:
        print("# WARNING: Base version not found defaulting BUILD_VERSION to 0.1.0")
        dirty_version = "0.1.0"
    # Strips trailing a0 from version.txt, not too sure why it's there in the
    # first place
    return re.sub(LEGACY_BASE_VERSION_SUFFIX_PATTERN, "", dirty_version)


def load_dep_info():
    global __cuda_version__
    global __cudnn_version__
    global __tensorrt_version__
    with open("dev_dep_versions.yml", "r") as stream:
        versions = yaml.safe_load(stream)
        if (gpu_arch_version := os.environ.get("CU_VERSION")) is not None:
            __cuda_version__ = (
                (gpu_arch_version[2:])[:-1] + "." + (gpu_arch_version[2:])[-1:]
            )
        else:
            __cuda_version__ = versions["__cuda_version__"]
        __cudnn_version__ = versions["__cudnn_version__"]
        __tensorrt_version__ = versions["__tensorrt_version__"]


load_dep_info()

dir_path = str(get_root_dir()) + "/py"

CXX11_ABI = False
JETPACK_VERSION = None
FX_ONLY = False
LEGACY = False
RELEASE = False
CI_BUILD = False

if "--fx-only" in sys.argv:
    FX_ONLY = True
    sys.argv.remove("--fx-only")

if "--legacy" in sys.argv:
    LEGACY = True
    sys.argv.remove("--legacy")

if "--release" in sys.argv:
    RELEASE = True
    sys.argv.remove("--release")

if (release_env_var := os.environ.get("RELEASE")) is not None:
    if release_env_var == "1":
        RELEASE = True

if (gpu_arch_version := os.environ.get("CU_VERSION")) is None:
    gpu_arch_version = f"cu{__cuda_version__.replace('.','')}"


if RELEASE:
    __version__ = os.environ.get("BUILD_VERSION")
else:
    __version__ = f"{get_base_version()}.dev0+{get_git_revision_short_hash()}"

if "--ci" in sys.argv:
    sys.argv.remove("--ci")
    if RELEASE:
        CI_BUILD = True

if (ci_env_var := os.environ.get("CI_BUILD")) is not None:
    if ci_env_var == "1":
        CI_BUILD = True

if "--use-cxx11-abi" in sys.argv:
    sys.argv.remove("--use-cxx11-abi")
    CXX11_ABI = True

if platform.uname().processor == "aarch64":
    if "--jetpack-version" in sys.argv:
        version_idx = sys.argv.index("--jetpack-version") + 1
        version = sys.argv[version_idx]
        sys.argv.remove(version)
        sys.argv.remove("--jetpack-version")
        if version == "4.5":
            JETPACK_VERSION = "4.5"
        elif version == "4.6":
            JETPACK_VERSION = "4.6"
        elif version == "5.0":
            JETPACK_VERSION = "5.0"

    if not JETPACK_VERSION:
        warnings.warn(
            "Assuming jetpack version to be 5.0, if not use the --jetpack-version option"
        )
        JETPACK_VERSION = "5.0"

    if not CXX11_ABI:
        warnings.warn(
            "Jetson platform detected but did not see --use-cxx11-abi option, if using a pytorch distribution provided by NVIDIA include this flag"
        )


def which(program):
    import os

    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


BAZEL_EXE = None
if not FX_ONLY:
    BAZEL_EXE = which("bazelisk.exe")

    if BAZEL_EXE is None:
        BAZEL_EXE = which("bazel.exe")
        if BAZEL_EXE is None:
            sys.exit("Could not find bazel in PATH")


def build_libtorchtrt_pre_cxx11_abi(develop=True, use_dist_dir=True, cxx11_abi=False):
    cmd = [BAZEL_EXE, "build"]
    cmd.append("//:libtorchtrt")
    if develop:
        cmd.append("--compilation_mode=dbg")
    else:
        cmd.append("--compilation_mode=opt")
    if use_dist_dir:
        cmd.append("--distdir=third_party/dist_dir/x86_64-linux-gnu")
    if not cxx11_abi:
        cmd.append("--config=python")
    else:
        print("using CXX11 ABI build")

    if JETPACK_VERSION == "4.5":
        cmd.append("--platforms=//toolchains:jetpack_4.5")
        print("Jetpack version: 4.5")
    elif JETPACK_VERSION == "4.6":
        cmd.append("--platforms=//toolchains:jetpack_4.6")
        print("Jetpack version: 4.6")
    elif JETPACK_VERSION == "5.0":
        cmd.append("--platforms=//toolchains:jetpack_5.0")
        print("Jetpack version: 5.0")

    if CI_BUILD:
        cmd.append("--platforms=//toolchains:ci_rhel_x86_64_linux")
        print("CI based build")

    print("building libtorchtrt")
    status_code = subprocess.run(cmd).returncode

    if status_code != 0:
        sys.exit(status_code)


def gen_version_file():
    with open(dir_path + "/torch_tensorrt/_version.py", "w") as f:
        print("creating version file")
        f.write('__version__ = "' + __version__ + '"\n')
        f.write('__cuda_version__ = "' + __cuda_version__ + '"\n')
        f.write('__cudnn_version__ = "' + __cudnn_version__ + '"\n')
        f.write('__tensorrt_version__ = "' + __tensorrt_version__ + '"\n')


def copy_libtorchtrt(multilinux=False):
    if not os.path.exists(dir_path + "/torch_tensorrt/lib"):
        os.makedirs(dir_path + "/torch_tensorrt/lib")

    print("copying library into module")
    if multilinux:
        copyfile(
            dir_path + "/build/libtrtorch_build/libtrtorch.so",
            dir_path + "/trtorch/lib/libtrtorch.so",
        )
    else:
        os.system(
            "tar -xzf "
            + dir_path
            + "/../bazel-bin/libtorchtrt.tar.gz --strip-components=1 -C "
            + dir_path
            + "/torch_tensorrt"
        )


class DevelopCommand(develop):
    description = "Builds the package and symlinks it into the PYTHONPATH"

    def initialize_options(self):
        develop.initialize_options(self)

    def finalize_options(self):
        develop.finalize_options(self)

    def run(self):
        if FX_ONLY:
            gen_version_file()
            develop.run(self)
        else:
            global CXX11_ABI
            build_libtorchtrt_pre_cxx11_abi(develop=True, cxx11_abi=CXX11_ABI)
            gen_version_file()
            copy_libtorchtrt()
            develop.run(self)


class InstallCommand(install):
    description = "Builds the package"

    def initialize_options(self):
        install.initialize_options(self)

    def finalize_options(self):
        install.finalize_options(self)

    def run(self):
        if FX_ONLY:
            gen_version_file()
            install.run(self)
        else:
            global CXX11_ABI
            build_libtorchtrt_pre_cxx11_abi(develop=False, cxx11_abi=CXX11_ABI)
            gen_version_file()
            copy_libtorchtrt()
            install.run(self)


class BdistCommand(bdist_wheel):
    description = "Builds the package"

    def initialize_options(self):
        bdist_wheel.initialize_options(self)

    def finalize_options(self):
        bdist_wheel.finalize_options(self)

    def run(self):
        global CXX11_ABI
        build_libtorchtrt_pre_cxx11_abi(develop=False, cxx11_abi=CXX11_ABI)
        gen_version_file()
        copy_libtorchtrt()
        bdist_wheel.run(self)


class EditableWheelCommand(editable_wheel):
    description = "Builds the package in development mode"

    def initialize_options(self):
        editable_wheel.initialize_options(self)

    def finalize_options(self):
        editable_wheel.finalize_options(self)

    def run(self):
        if FX_ONLY:
            gen_version_file()
            editable_wheel.run(self)
        else:
            global CXX11_ABI
            build_libtorchtrt_pre_cxx11_abi(develop=True, cxx11_abi=CXX11_ABI)
            gen_version_file()
            copy_libtorchtrt()
            editable_wheel.run(self)


class CleanCommand(Command):
    """Custom clean command to tidy up the project root."""

    PY_CLEAN_DIRS = [
        "./build",
        "./dist",
        "./torch_tensorrt/__pycache__",
        "./torch_tensorrt/lib",
        "./torch_tensorrt/include",
        "./torch_tensorrt/bin",
        "./*.pyc",
        "./*.tgz",
        "./*.egg-info",
    ]
    PY_CLEAN_FILES = [
        "./torch_tensorrt/*.so",
        "./torch_tensorrt/_version.py",
        "./torch_tensorrt/BUILD",
        "./torch_tensorrt/WORKSPACE",
        "./torch_tensorrt/LICENSE",
    ]
    description = "Command to tidy up the project root"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        for path_spec in self.PY_CLEAN_DIRS:
            # Make paths absolute and relative to this path
            abs_paths = glob.glob(os.path.normpath(os.path.join(dir_path, path_spec)))
            for path in [str(p) for p in abs_paths]:
                if not path.startswith(dir_path):
                    # Die if path in CLEAN_FILES is absolute + outside this directory
                    raise ValueError("%s is not a path inside %s" % (path, dir_path))
                print("Removing %s" % os.path.relpath(path))
                rmtree(path)

        for path_spec in self.PY_CLEAN_FILES:
            # Make paths absolute and relative to this path
            abs_paths = glob.glob(os.path.normpath(os.path.join(dir_path, path_spec)))
            for path in [str(p) for p in abs_paths]:
                if not path.startswith(dir_path):
                    # Die if path in CLEAN_FILES is absolute + outside this directory
                    raise ValueError("%s is not a path inside %s" % (path, dir_path))
                print("Removing %s" % os.path.relpath(path))
                os.remove(path)


ext_modules = []

packages = [
    "torch_tensorrt",
    "torch_tensorrt.dynamo",
    "torch_tensorrt.dynamo.backend",
    "torch_tensorrt.dynamo.conversion",
    "torch_tensorrt.dynamo.conversion.impl",
    "torch_tensorrt.dynamo.conversion.impl.activation",
    "torch_tensorrt.dynamo.conversion.impl.condition",
    "torch_tensorrt.dynamo.conversion.impl.elementwise",
    "torch_tensorrt.dynamo.conversion.impl.normalization",
    "torch_tensorrt.dynamo.conversion.impl.slice",
    "torch_tensorrt.dynamo.conversion.impl.unary",
    "torch_tensorrt.dynamo.lowering",
    "torch_tensorrt.dynamo.lowering.passes",
    "torch_tensorrt.dynamo.partitioning",
    "torch_tensorrt.dynamo.runtime",
    "torch_tensorrt.dynamo.tools",
    "torch_tensorrt.fx",
    "torch_tensorrt.fx.converters",
    "torch_tensorrt.fx.converters.impl",
    "torch_tensorrt.fx.passes",
    "torch_tensorrt.fx.tools",
    "torch_tensorrt.fx.tracer",
    "torch_tensorrt.fx.tracer.acc_tracer",
    "torch_tensorrt.fx.tracer.dispatch_tracer",
]

package_dir = {
    "torch_tensorrt": "py/torch_tensorrt",
    "torch_tensorrt.dynamo": "py/torch_tensorrt/dynamo",
    "torch_tensorrt.dynamo.backend": "py/torch_tensorrt/dynamo/backend",
    "torch_tensorrt.dynamo.conversion": "py/torch_tensorrt/dynamo/conversion",
    "torch_tensorrt.dynamo.conversion.impl": "py/torch_tensorrt/dynamo/conversion/impl",
    "torch_tensorrt.dynamo.conversion.impl.activation": "py/torch_tensorrt/dynamo/conversion/impl/activation",
    "torch_tensorrt.dynamo.conversion.impl.condition": "py/torch_tensorrt/dynamo/conversion/impl/condition",
    "torch_tensorrt.dynamo.conversion.impl.elementwise": "py/torch_tensorrt/dynamo/conversion/impl/elementwise",
    "torch_tensorrt.dynamo.conversion.impl.normalization": "py/torch_tensorrt/dynamo/conversion/impl/normalization",
    "torch_tensorrt.dynamo.conversion.impl.slice": "py/torch_tensorrt/dynamo/conversion/impl/slice",
    "torch_tensorrt.dynamo.conversion.impl.unary": "py/torch_tensorrt/dynamo/conversion/impl/unary",
    "torch_tensorrt.dynamo.lowering": "py/torch_tensorrt/dynamo/lowering",
    "torch_tensorrt.dynamo.lowering.passes": "py/torch_tensorrt/dynamo/lowering/passes",
    "torch_tensorrt.dynamo.partitioning": "py/torch_tensorrt/dynamo/partitioning",
    "torch_tensorrt.dynamo.runtime": "py/torch_tensorrt/dynamo/runtime",
    "torch_tensorrt.dynamo.tools": "py/torch_tensorrt/dynamo/tools",
    "torch_tensorrt.fx": "py/torch_tensorrt/fx",
    "torch_tensorrt.fx.converters": "py/torch_tensorrt/fx/converters",
    "torch_tensorrt.fx.converters.impl": "py/torch_tensorrt/fx/converters/impl",
    "torch_tensorrt.fx.passes": "py/torch_tensorrt/fx/passes",
    "torch_tensorrt.fx.tools": "py/torch_tensorrt/fx/tools",
    "torch_tensorrt.fx.tracer": "py/torch_tensorrt/fx/tracer",
    "torch_tensorrt.fx.tracer.acc_tracer": "py/torch_tensorrt/fx/tracer/acc_tracer",
    "torch_tensorrt.fx.tracer.dispatch_tracer": "py/torch_tensorrt/fx/tracer/dispatch_tracer",
}

package_data = {}

if not FX_ONLY:
    ext_modules += [
        cpp_extension.CUDAExtension(
            "torch_tensorrt._C",
            [
                "py/" + f
                for f in [
                    "torch_tensorrt/csrc/torch_tensorrt_py.cpp",
                    "torch_tensorrt/csrc/tensorrt_backend.cpp",
                    "torch_tensorrt/csrc/tensorrt_classes.cpp",
                    "torch_tensorrt/csrc/register_tensorrt_classes.cpp",
                ]
            ],
            library_dirs=[
                (dir_path + "/torch_tensorrt/lib/"),
                "/opt/conda/lib/python3.6/config-3.6m-x86_64-linux-gnu",
            ],
            libraries=["torch_tensorrt.dll.if"],
            include_dirs=[
                dir_path + "torch_tensorrt/csrc",
                dir_path + "torch_tensorrt/include",
                dir_path + "/../bazel-TRTorch/external/tensorrt/include",
                dir_path + "/../bazel-Torch-TensorRT/external/tensorrt/include",
                dir_path + "/../bazel-TensorRT/external/tensorrt/include",
                dir_path + "/../bazel-tensorrt/external/tensorrt/include",
                dir_path + "/../",
                "/usr/local/cuda",
            ],
            extra_compile_args=["/D", "NO_EXPORT", f"-D_GLIBCXX_USE_CXX11_ABI={int(CXX11_ABI)}"],
            extra_link_args=["/OPT:NOREF", f"-D_GLIBCXX_USE_CXX11_ABI={int(CXX11_ABI)}"],
            undef_macros=["NDEBUG"],
        )
    ]

    packages += [
        "torch_tensorrt.ts",
    ]

    package_dir.update(
        {
            "torch_tensorrt.ts": "py/torch_tensorrt/ts",
        }
    )

    package_data.update(
        {
            "torch_tensorrt": [
                "BUILD",
                "WORKSPACE",
                "include/torch_tensorrt/*.h",
                "include/torch_tensorrt/core/*.h",
                "include/torch_tensorrt/core/conversion/*.h",
                "include/torch_tensorrt/core/conversion/conversionctx/*.h",
                "include/torch_tensorrt/core/conversion/converters/*.h",
                "include/torch_tensorrt/core/conversion/evaluators/*.h",
                "include/torch_tensorrt/core/conversion/tensorcontainer/*.h",
                "include/torch_tensorrt/core/conversion/var/*.h",
                "include/torch_tensorrt/core/ir/*.h",
                "include/torch_tensorrt/core/lowering/*.h",
                "include/torch_tensorrt/core/lowering/passes/*.h",
                "include/torch_tensorrt/core/partitioning/*.h",
                "include/torch_tensorrt/core/partitioning/segmentedblock/*.h",
                "include/torch_tensorrt/core/partitioning/partitioninginfo/*.h",
                "include/torch_tensorrt/core/partitioning/partitioningctx/*.h",
                "include/torch_tensorrt/core/plugins/*.h",
                "include/torch_tensorrt/core/plugins/impl/*.h",
                "include/torch_tensorrt/core/runtime/*.h",
                "include/torch_tensorrt/core/util/*.h",
                "include/torch_tensorrt/core/util/logging/*.h",
                "bin/*",
                "lib/*",
            ]
        }
    )

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="torch_tensorrt",
    ext_modules=ext_modules,
    version=__version__,
    cmdclass={
        "install": InstallCommand,
        "clean": CleanCommand,
        "develop": DevelopCommand,
        "build_ext": cpp_extension.BuildExtension,
        "bdist_wheel": BdistCommand,
        "editable_wheel": EditableWheelCommand,
    },
    zip_safe=False,
    packages=packages,
    package_dir=package_dir,
    include_package_data=False,
    package_data=package_data,
    exclude_package_data={
        "": [
            "py/torch_tensorrt/csrc/*.cpp",
            "py/torch_tensorrt/fx/test*",
            "torch_tensorrt/csrc/*.cpp",
            "torch_tensorrt/fx/test*",
            "test*",
            "*.cpp",
        ],
        "torch_tensorrt": [
            "py/torch_tensorrt/csrc/*.cpp",
            "py/torch_tensorrt/fx/test*",
            "torch_tensorrt/csrc/*.cpp",
            "torch_tensorrt/fx/test*",
            "test*",
            "*.cpp",
        ],
        "torch_tensorrt.dynamo": ["test/*.py"],
        "torch_tensorrt.fx": ["test/*.py"],
    },
)
