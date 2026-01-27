# Change Log

## [0.1.6] - 2026-01-27

### Changed

- Proof of concept for campaign statistics completed, moved to OpenAPI.

## [0.1.5] - 2026-01-27

### Added

- Implemented 500ms rate limiting for all ZKillboard API requests.
- Simplified task locking mechanism for `pull_zkillboard_data` and `repair_campaign_killmails`.

## [0.1.4] - 2026-01-26

### Added

- Implemented hierarchy-based entity de-duplication for ZKillboard data pull task.
- Optimized entity selection logic to reduce redundant API requests for campaigns with location or target filters.

## [0.1.3] - 2026-01-26

### Fixed

- Optimized task performance with batching and in-memory caching.
- Implemented concurrency control using cache-based locks.

## [0.1.2] - 2026-01-26

### Fixed

- Optimized lookback logic to use `pastSeconds` API for recent data.
- Added `last_run` tracking to `Campaign` model.

## [0.1.1] - 2026-01-25

### Fixed

- Resolved DataTables warning on Campaign Details page when ship statistics are empty.

## [0.1.0] - 2026-01-25

### Added

- Initial version
