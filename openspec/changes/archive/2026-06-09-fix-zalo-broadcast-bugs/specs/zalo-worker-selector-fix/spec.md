## ADDED Requirements

### Requirement: Worker selector must be visible when workers are available
The worker selector dropdown SHALL be rendered when workers are available, not permanently hidden.

#### Scenario: Worker goes offline
- **WHEN** a worker's status is "offline" and other workers are available
- **THEN** the user SHALL see a dropdown to select a different worker

### Requirement: Worker status display must show accurate fallback
The worker status IIFE SHALL correctly show "Tự động" when no matching worker is found.

#### Scenario: No worker matches selectedWorkerId
- **WHEN** `flow.selectedWorkerId` does not match any worker
- **THEN** the display SHALL show "Tự động", not a fake worker's status
