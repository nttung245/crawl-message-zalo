## ADDED Requirements

### Requirement: Filter image URLs by file extension

The system SHALL filter image URLs to include only `.jpeg`, `.jpg`, and `.png` files. All other formats (`.gif`, `.webp`, `.svg`, `.bmp`, data URLs with non-image MIME types) MUST be excluded.

#### Scenario: Mixed image types in message
- **WHEN** a message has image URLs: `["photo.jpg", "sticker.gif", "banner.png", "icon.svg"]`
- **THEN** only `["photo.jpg", "banner.png"]` are kept

#### Scenario: Data URL images
- **WHEN** a message has data URL images like `data:image/png;base64,...` and `data:image/gif;base64,...`
- **THEN** only the PNG data URL is kept

#### Scenario: No qualifying images
- **WHEN** a message has only `.gif` and `.webp` images
- **THEN** image list is empty and no images are downloaded

### Requirement: Download filtered images for confirmed listings only

The system SHALL download images ONLY for messages that passed the text classifier. Images MUST be read from the existing `zalo_message_assets` table (already stored by the crawl pipeline), not re-extracted from Zalo DOM.

#### Scenario: Listing message with images
- **WHEN** classifier returns `is_listing: true` AND message has 3 `.jpg` assets in `zalo_message_assets`
- **THEN** system reads `storage_url` from assets table and downloads all 3 images

#### Scenario: Listing message with no images
- **WHEN** classifier returns `is_listing: true` AND message has 0 image assets
- **THEN** listing is created without images (no download attempted)

### Requirement: Re-upload filtered images to GoDaNang storage

The system SHALL upload filtered images to GoDaNang's Supabase Storage bucket and store the resulting URLs in the `villas.images` array.

#### Scenario: Images uploaded to GoDaNang storage
- **WHEN** 3 filtered images are downloaded from crawler storage
- **THEN** all 3 are uploaded to GoDaNang Supabase Storage under path `apartments/{slug}/{filename}`
- **AND** the resulting storage URLs are set in the `villas.images` JSONB array
