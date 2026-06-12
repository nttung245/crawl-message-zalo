## ADDED Requirements

### Requirement: Default villa configuration

The system SHALL provide a centralized default configuration for GoDaNang villa fields that the LLM extractor does not determine from message text.

- Default values SHALL be defined in a Python module `default_config.py` as a dictionary.
- The Stage 2 extractor SHALL merge LLM-extracted fields with defaults, preferring LLM output when both exist.
- Changing a default SHALL NOT require modifying the LLM prompt.
- The default configuration SHALL include at minimum: `commission_percent`, `amenities`, `type`, `listing_status`.

#### Scenario: LLM extracts price, default fills commission

- **WHEN** the LLM extracts `price: 8000000` from a message but does not output a commission field
- **THEN** the merged record uses `commission_percent: 12` from defaults and `price: 8000000` from LLM

#### Scenario: LLM overrides default amenity

- **WHEN** the LLM extracts `amenities: ["hồ bơi", "wifi"]` from a message
- **THEN** the merged record uses the LLM's amenity list, not the default `["bếp ga", "phòng tắm riêng", "wifi", "máy lạnh"]`

#### Scenario: All fields missing from LLM

- **WHEN** the LLM returns a minimal listing with only `title` and `price`
- **THEN** the merged record contains `title` and `price` from LLM, all other fields filled from defaults

#### Scenario: Default config is importable without side effects

- **WHEN** `from app.modules.apartment_agent.default_config import DEFAULT_VILLA` is executed
- **THEN** no network calls or file I/O occur
