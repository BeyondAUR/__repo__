#! /usr/bin/env python3
import contextlib
import os
import pathlib
import shutil
import subprocess
import tempfile

from collections.abc import Generator, Iterable

import typer

PROJECT_ROOT = pathlib.Path(__file__).parent
TMP_FOLDER = PROJECT_ROOT.joinpath("tmp")
NSPAWN_FOLDER = PROJECT_ROOT.joinpath("nspawn")
NSPAWN_INITIALIZED_MARKER_FILENAME = NSPAWN_FOLDER.joinpath("initialized.json")
CONFIG_FOLDER = PROJECT_ROOT.joinpath("config")
MAKEPKG_CONFIG_FILENAME = CONFIG_FOLDER.joinpath("makepkg.conf")
PACMAN_CONFIG_FILENAME = CONFIG_FOLDER.joinpath("pacman.conf")

PKGS_FOLDER = PROJECT_ROOT.joinpath("pkgs")

ESSENTIAL_PACKAGES = (
    "hx-ghcup-hs",
    "rustup",
    "git",
    "cmake",
    "rsync",
    "base-devel",
)


@contextlib.contextmanager
def temporary_dir_for_pkgbuild() -> Generator[pathlib.Path, None, None]:
    with tempfile.TemporaryDirectory(dir=TMP_FOLDER, prefix="pb-") as tmp_dir:
        pkgbuild_top_dir = pathlib.Path(tmp_dir).joinpath("pkgbuild_code")
        try:
            yield pkgbuild_top_dir
        finally:
            pass


def clone_pkgbuild_code_to_dir(pkgbuild_top_dir: pathlib.Path, git_url: str):
    subprocess.run(
        ["git", "clone", git_url, pkgbuild_top_dir.name],
        cwd=pkgbuild_top_dir.parent,
        shell=False,
        check=False,
    )


def auto_initialize_nspawn_folder():
    if not NSPAWN_INITIALIZED_MARKER_FILENAME.is_file():
        nspawn_root_top = NSPAWN_FOLDER.joinpath("root")
        subprocess.run(
            [
                "mkarchroot",
                "-C",
                PACMAN_CONFIG_FILENAME,
                "-M",
                MAKEPKG_CONFIG_FILENAME,
                nspawn_root_top,
            ]
            + list(ESSENTIAL_PACKAGES),
            cwd=NSPAWN_FOLDER,
            shell=False,
            check=True,
        )
        NSPAWN_INITIALIZED_MARKER_FILENAME.write_text("0")


def update_nspawn_folder():
    for nspawn_top in filter(lambda x: x.is_dir(), NSPAWN_FOLDER.iterdir()):
        subprocess.run(
            [
                "arch-nspawn",
                "-C",
                PACMAN_CONFIG_FILENAME.__fspath__(),
                "-M",
                MAKEPKG_CONFIG_FILENAME.__fspath__(),
                nspawn_top,
                "pacman",
                "--noconfirm",
                "-Syu",
            ]
            + list(ESSENTIAL_PACKAGES)
        )


def execute_pkgbuild(pkgbuild_top_dir: pathlib.Path) -> Iterable[pathlib.Path]:
    auto_initialize_nspawn_folder()
    # update
    update_nspawn_folder()
    # build
    subprocess.run(
        [
            "makechrootpkg",
            "-r",
            NSPAWN_FOLDER,
        ],
        cwd=pkgbuild_top_dir,
        shell=False,
        check=True,
    )
    package_filenames = pkgbuild_top_dir.glob("*.pkg.tar.*")
    return package_filenames


def architecture_of_package(package_filename: pathlib.Path) -> str:
    name = package_filename.name
    _pkg_sec_idx = name.rfind(".pkg")
    _front = name[:_pkg_sec_idx]
    _last_dash_idx = _front.rfind("-")
    _arch = _front[_last_dash_idx + 1 :]
    return _arch


def move_built_packages(package_filenames: Iterable[pathlib.Path]):
    for from_package_filename in package_filenames:
        _arch = architecture_of_package(from_package_filename)
        if _arch == "any":
            to_package_filenames = [
                _t / from_package_filename.name
                for _t in PKGS_FOLDER.iterdir()
                if _t.is_dir()
            ]
        else:
            to_package_filenames = [
                PKGS_FOLDER.joinpath(_arch, from_package_filename.name)
            ]

        for to_package_filename in to_package_filenames:
            db_filename = to_package_filename.with_name("beyondaur.db.tar.gz")
            if not to_package_filename.is_file():
                shutil.copy(from_package_filename, to_package_filename)
                subprocess.run(["repo-add", db_filename, to_package_filename])
                print(f"Move {from_package_filename.name}")
            else:
                print(f"{from_package_filename.name} already existed in pkgs")
        os.unlink(from_package_filename)


def main(pkg_name: str):
    if "/" in pkg_name:
        pkg_git_url = pkg_name
    else:
        pkg_git_url = f"https://github.com/BeyondAUR/{pkg_name}.git"

    with temporary_dir_for_pkgbuild() as pkgbuild_codespace:
        clone_pkgbuild_code_to_dir(pkgbuild_codespace, pkg_git_url)
        package_filenames = execute_pkgbuild(pkgbuild_codespace)
        move_built_packages(package_filenames)

    print("Now commit and push this git worktree")


if __name__ == "__main__":
    typer.run(main)
