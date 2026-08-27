# Third-party notices

ScreenTuner itself is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md).
The distributed `ScreenTuner.exe` additionally contains, or interacts with, the following.

## Python (bundled)

The released executable bundles the CPython runtime and parts of its standard library,
including Tcl/Tk for the settings window. Python is distributed under the
**PSF License Agreement**, Copyright (c) 2001-2026 Python Software Foundation.
Full text: <https://docs.python.org/3/license.html>

Tcl/Tk is distributed under a BSD-style licence, Copyright (c) Regents of the University
of California, Sun Microsystems Inc., and other parties.

## PyInstaller (build tool)

The executable is produced with PyInstaller, whose bootloader is included in the output.
PyInstaller is GPL 2.0-or-later **with an exception** that explicitly permits using it to
build and distribute non-GPL, including proprietary, applications.
Full text: <https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>

## Inno Setup (build tool)

The optional installer is produced with Inno Setup, Copyright (c) 1997-2026 Jordan Russell.
Its bootstrap code is included in the generated setup executable, under a licence that
permits distributing the installers it creates, commercially or otherwise.
Full text: <https://jrsoftware.org/files/is/license.txt>

## NVIDIA NVAPI (NOT bundled)

Digital vibrance is set through NVIDIA's NVAPI. **No NVIDIA code, header, library or DLL
is redistributed with ScreenTuner.** At runtime the app looks up `nvapi64.dll` — already
present as part of the user's own installed NVIDIA driver — and resolves the entry points
it needs through the driver's `nvapi_QueryInterface` export. Nothing NVIDIA-owned is
copied, shipped, or included in this repository.

NVIDIA, GeForce and NVAPI are trademarks of NVIDIA Corporation. ScreenTuner is not
affiliated with, endorsed by, or sponsored by NVIDIA Corporation.
