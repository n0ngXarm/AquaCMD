#!/bin/sh
set -eu
aqua_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
aqua_output=${1:?Usage: build-windows.sh /absolute/owned-output-directory}
case "$aqua_output" in /*) ;; *) echo 'An absolute output directory is required' >&2; exit 2;; esac
mkdir -p "$aqua_output"
aqua_dotnet=${AQUA_DOTNET:-dotnet}
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false
"$aqua_dotnet" run --project "$aqua_root/windows-reader/Tests/Aqua.Reader.Tests.csproj" -c Release
"$aqua_dotnet" publish "$aqua_root/windows-reader/Windows/Aqua.Reader.Windows.csproj" -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:PublishTrimmed=false -p:DebugType=None -p:DebugSymbols=false -o "$aqua_output"
# Retain redistribution notices for the Microsoft runtime packs bundled in the EXE.
aqua_packages=${NUGET_PACKAGES:-${HOME}/.nuget/packages}
for aqua_package in microsoft.netcore.app.runtime.win-x64 microsoft.windowsdesktop.app.runtime.win-x64; do
 for aqua_version in "$aqua_packages/$aqua_package"/*; do
  [ -d "$aqua_version" ] || continue
  aqua_version_name=$(basename "$aqua_version")
  for aqua_notice in LICENSE LICENSE.TXT THIRD-PARTY-NOTICES.TXT; do
   [ -f "$aqua_version/$aqua_notice" ] || continue
   cp "$aqua_version/$aqua_notice" "$aqua_output/$aqua_package-$aqua_version_name-$aqua_notice.txt"
  done
 done
done
