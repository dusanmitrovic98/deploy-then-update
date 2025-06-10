# Changelog

## [Unreleased]

## [v0.0.7] - 2025-06-10
### Fixed
- Navigation sidebar now correctly highlights the active tab when switching between Dashboard, Explorer, Terminal, and Configuration. The highlight no longer appears on the wrong button due to section headings or order.

## [0.0.6] - 2025-06-10
### Added
- Terminal "Refresh" button now deletes terminal.log before reloading, matching manual cleanup workflow.
### Changed
- Terminal panel and console now use the full available height for a better visual experience.
### Fixed
- Improved usability and consistency in the terminal panel.

## [v0.0.5] - 2025-06-10
### Fixed
- File explorer now displays folders and files in a proper nested, collapsible tree structure.
- Improved: .git and other deep folder structures are now shown as expected, restoring a clean and intuitive file tree view.

## [v0.0.4] - 2025-06-10
### Changed
- Made all dashboard quick actions (start, stop, restart, update) call the backend API and reflect real system state.
- Replaced all simulated/demo JavaScript logic with real API calls for config, terminal, and scripts.
- Authentication is now enforced and required for all API requests.
- Improved error handling and user feedback for all actions.

## [v0.0.3] - 2025-06-10
### Changed
- Complete redesign of the dashboard interface.
- Improved user experience with a more intuitive layout.

## [v0.0.2] - 2025-06-10
### Changed
- Refactored dashboard.html: removed duplicate CSS and JavaScript, consolidated file manager functions, and ensured the file editor panel is only visible when the Explorer tab is active.

## [v0.0.1] - 2025-06-10
### Added
- Initial release.
- Basic project structure and setup.
- Core deployment and update functionality.
- Documentation and usage instructions.