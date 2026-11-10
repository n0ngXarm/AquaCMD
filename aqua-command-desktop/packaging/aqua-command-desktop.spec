Name: aqua-command-desktop
Version: 0.9.0
Release: 1%{?dist}
Summary: Native read-only AQUA snapshot collector, SCADA monitor and LAN relay
License: MIT
URL: https://github.com/n0ngXarm/AquaCMD
Source0: %{name}-%{version}.tar.gz
BuildArch: noarch
Prefix: /usr
Requires: python3 >= 3.11
Requires: python3-gobject >= 3.42
Requires: gtk4 >= 4.10
Requires: webkitgtk6.0
Requires: python3-cairo
Requires: nodejs22-bin >= 22.13
Requires: hicolor-icon-theme
Recommends: python3-cryptography
Recommends: python3-asyncua
%global debug_package %{nil}
%global _build_id_links none
%description
Native GTK4 desktop frontend for read-only local runtime CSV collection,
SCADA monitoring, durable queues and authenticated forwarding through explicitly
enrolled LAB gateways. No browser, webview or dashboard HTTP listener is launched.
WinCC/PLC writes are not supported. Default idle; separate operator approval
is required for capture and forwarding. LAB data is explicitly selected.
Direct WinCC Runtime remains unavailable pending an approved read channel.
%prep
%setup -q
%build
# Python/JavaScript source uses distribution runtimes; no native compilation.
%install
mkdir -p %{buildroot}%{_datadir}/%{name}/desktop
mkdir -p %{buildroot}%{_datadir}/%{name}/backend/bin
mkdir -p %{buildroot}%{_bindir} %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
mkdir -p %{buildroot}%{_datadir}/%{name}/backend/src

# Backend LAN relay service
cp -a backend/src/lan %{buildroot}%{_datadir}/%{name}/backend/src/
install -m 644 backend/package.json %{buildroot}%{_datadir}/%{name}/backend/
install -m 644 backend/bin/aqua-service.js %{buildroot}%{_datadir}/%{name}/backend/bin/

# Python collector modules, shared source and runtime configuration
cp -a src %{buildroot}%{_datadir}/%{name}/
cp -a collector %{buildroot}%{_datadir}/%{name}/
cp -a config %{buildroot}%{_datadir}/%{name}/

# Desktop frontend application runtime
cp -a desktop/* %{buildroot}%{_datadir}/%{name}/desktop/
rm -rf %{buildroot}%{_datadir}/%{name}/desktop/tests
find %{buildroot}%{_datadir}/%{name} -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find %{buildroot}%{_datadir}/%{name} -name "*.pyc" -delete
find %{buildroot}%{_datadir}/%{name} -name "*test*.py" -delete
find %{buildroot}%{_datadir}/%{name} -name "*.tmp" -delete

# Standardize permissions
find %{buildroot}%{_datadir}/%{name} -type d -exec chmod 755 {} +
find %{buildroot}%{_datadir}/%{name} -type f -exec chmod 644 {} +

# Launcher, desktop entry, and icon
install -m 755 packaging/aqua-command %{buildroot}%{_bindir}/aqua-command
install -m 644 packaging/org.aquacommand.Desktop.desktop %{buildroot}%{_datadir}/applications/
install -m 644 packaging/icons/org.aquacommand.Desktop.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/
%files
%license LICENSE
%doc README.md VERIFICATION.md docs
%{_bindir}/aqua-command
%{_datadir}/%{name}
%{_datadir}/applications/org.aquacommand.Desktop.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.aquacommand.Desktop.svg
%changelog
* Thu Oct 29 2026 AQUA COMMAND contributors - 0.9.0-1
- Complete GTK4 and WebKitGTK 6.0 desktop packaging with full dependency closure.
- Explicit actual CSV Agent and HTTPS enrolled Gateway with manual receive/send permissions.
- Read-only runtime v3 custody and per-item OPC timestamps; no simulated normal workflow.
