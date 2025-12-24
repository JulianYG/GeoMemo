# GeoMemo - Personal GeoGuessr Map Creator

A fun project that extracts location data from your Apple Photos library and creates a personal GeoGuessr map!

## Features

- 📍 Extracts GPS coordinates from all photos and videos in your Apple Photos library
- 📊 Exports location data to CSV (for GeoGuessr) and GeoJSON (for visualization)
- 📈 Provides statistics about your photo locations
- 🎯 Ready-to-use for creating custom GeoGuessr maps
- 🔍 Filters out screenshots and non-camera media
- 📅 Optional date range filtering
- 🔄 Optional deduplication to avoid duplicate locations

## Requirements

- macOS (required for osxphotos library)
- Python 3.10 or later
- Apple Photos library with photos containing GPS data

## Installation

1. Clone or download this repository

2. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Quick Start

Run the extraction script:
```bash
python location_extractor.py
```

This will:
- Scan your Apple Photos library
- Extract all photos/videos with GPS coordinates
- Display statistics
- **Note**: By default, no files are exported. Use `--csv` and/or `--geojson` to export files.

### Basic Examples

```bash
# Show statistics only (no file export)
python location_extractor.py

# Export to CSV only
python location_extractor.py --csv photo_locations.csv

# Export to GeoJSON only
python location_extractor.py --geojson photo_locations.geojson

# Export both CSV and GeoJSON
python location_extractor.py --csv locations.csv --geojson locations.geojson
```

### Advanced Options

```bash
# Filter by date range
python location_extractor.py --start-from 2020-01-01 --end-on 2023-12-31 --csv locations.csv

# Remove duplicate locations (same coordinates rounded to 6 decimal places)
python location_extractor.py --dedupe --csv locations.csv

# More aggressive deduplication (5 decimal places, ~1 meter precision)
python location_extractor.py --dedupe --dedupe-precision 5 --csv locations.csv

# Use a specific Photos library database
python location_extractor.py --photos-db /path/to/Photos.sqlite --csv locations.csv

# Combine multiple options
python location_extractor.py \
  --start-from 2020-01-01 \
  --end-on 2023-12-31 \
  --dedupe \
  --csv locations.csv \
  --geojson locations.geojson
```

### Command-Line Options

| Option | Description |
|--------|-------------|
| `--csv PATH` | Export location data to CSV file (optional, no default) |
| `--geojson PATH` | Export location data to GeoJSON file (optional, no default) |
| `--start-from YYYY-MM-DD` | Filter photos from this date onwards (inclusive) |
| `--end-on YYYY-MM-DD` | Filter photos up to this date (inclusive) |
| `--dedupe` | Remove duplicate locations (same coordinates) |
| `--dedupe-precision N` | Precision for deduplication in decimal places (default: 6, ~0.1m) |
| `--photos-db PATH` | Path to Photos library database (uses default if not specified) |

### Using the Module Directly

You can also use the `LocationExtractor` class in your own scripts:

```python
from location_extractor import LocationExtractor

# Initialize extractor
extractor = LocationExtractor()

# Extract locations with date filtering
locations = extractor.extract_locations(
    start_date='2020-01-01',
    end_date='2023-12-31'
)

# Deduplicate locations
locations = extractor.deduplicate_locations(locations, precision=6)

# Export to files
extractor.export_to_csv(locations, 'my_locations.csv')
extractor.export_to_geojson(locations, 'my_locations.geojson')

# Get statistics
stats = extractor.get_statistics(locations)
print(f"Found {stats['total']} photos with locations")
```

## Output Files

### CSV Format
Simple two-column format:
- Latitude
- Longitude

This CSV can be imported directly into GeoGuessr's Map Maker.

**Example:**
```csv
Latitude,Longitude
37.7749,-122.4194
40.7128,-74.0060
```

### GeoJSON Format
GeoJSON format with features grouped by region:
- FeatureCollection with multiple Features (one per region)
- Each Feature has a MultiPoint geometry containing coordinates for that region
- Properties include the region name

**Example structure:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "region": "United States"
      },
      "geometry": {
        "type": "MultiPoint",
        "coordinates": [
          [-122.4194, 37.7749],
          [-74.0060, 40.7128]
        ]
      }
    }
  ]
}
```

Useful for:
- Mapping visualization tools (Leaflet, Mapbox, etc.)
- GIS software
- Custom web applications

## Creating Your GeoGuessr Map

1. Go to [GeoGuessr Map Maker](https://geoguessr.com/map-maker)
2. Click "Create a new map"
3. Import your `photo_locations.csv` file
4. Customize your map (name, description, etc.)
5. Save and start playing!

## Notes

- The first run may take a while if you have a large Photos library
- Only photos/videos with GPS coordinates will be included
- Photos with coordinates (0, 0) or null coordinates are automatically excluded
- Screenshots and imported media without camera EXIF data are filtered out
- Photos without dates are excluded when using date range filtering
- Region information comes from Apple Photos metadata (if available), otherwise set to "Unknown"
- Deduplication rounds coordinates to the specified precision to identify duplicates

## Troubleshooting

**Permission Errors**: Make sure Terminal/iTerm has permission to access your Photos library in System Preferences > Privacy & Security > Photos.

**No Locations Found**: Ensure your photos have GPS metadata. Photos taken with GPS-enabled devices (iPhones, most modern cameras) will have this data.

**Database Access Issues**: If you have multiple Photos libraries, you may need to specify the database path using `--photos-db`.

## License

MIT License - feel free to use and modify!

## Credits

Built using [osxphotos](https://github.com/RhetTbull/osxphotos) by RhetTbull.

