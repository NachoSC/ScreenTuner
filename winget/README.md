# winget manifests

Submitting to the community repo makes `winget install ScreenTuner` work for everyone.

**Order matters** — the manifest points at a download URL and its hash, so the GitHub
release has to exist first:

1. Tag and publish the release, attaching `ScreenTuner-<version>-setup.exe`.
2. Check `InstallerUrl` here matches the real asset URL.
3. Recompute the hash and paste it into `InstallerSha256`:
   ```powershell
   (Get-FileHash .\dist\installer\ScreenTuner-1.0.0-setup.exe -Algorithm SHA256).Hash
   ```
4. Validate and test locally:
   ```powershell
   winget validate --manifest .\winget\1.0.0
   winget install --manifest .\winget\1.0.0
   ```
5. Open a PR to [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) placing
   these three files at
   `manifests/n/Nachsilva/ScreenTuner/1.0.0/`.

`wingetcreate update` automates steps 2-5 for later versions.

Note: winget submission does not require code signing, but an unsigned installer will
still trigger SmartScreen on direct downloads.
