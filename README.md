# GeoMemo - Personal GeoGuessr Map Creator

A fun project that extracts location data from your Apple Photos library and creates a personal GeoGuessr map!

## Features

- 📍 Extracts GPS coordinates from all photos and videos in your Apple Photos library
- 📊 Exports location data to CSV (for GeoGuessr) and GeoJSON (for visualization)
- 📈 Provides statistics about your photo locations
- 🎯 Ready-to-use for creating custom GeoGuessr maps

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

### Using the Module Directly

You can also use the `LocationExtractor` class in your own scripts:

```python
from location_extractor import LocationExtractor

# Initialize extractor
extractor = LocationExtractor()

# Extract locations
locations = extractor.extract_locations()

# Export to files
extractor.export_to_csv(locations, 'my_locations.csv')
extractor.export_to_geojson(locations, 'my_locations.geojson')

# Get statistics
stats = extractor.get_statistics(locations)
print(f"Found {stats['total']} photos with locations")
```

### Command-Line Options

The `location_extractor.py` module can also be run directly with options:

```bash
# Show statistics only (no file export)
python location_extractor.py --stats-only

# Specify custom output paths
python location_extractor.py --csv my_locations.csv --geojson my_locations.geojson

# Use a specific Photos library database
python location_extractor.py --photos-db /path/to/Photos.sqlite
```

## Output Files

### CSV Format (`photo_locations.csv`)
Simple two-column format:
- Latitude
- Longitude

This CSV can be imported directly into GeoGuessr's Map Maker.

### GeoJSON Format (`photo_locations.geojson`)
Simplified GeoJSON format with a single MultiPoint feature containing all coordinates:
- FeatureCollection with one Feature
- MultiPoint geometry containing all [longitude, latitude] coordinates
- Empty properties object

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
- Photos with coordinates (0, 0) are automatically excluded as they're likely invalid
- The script requires access to your Photos library (you may need to grant permissions)

## Troubleshooting

**Permission Errors**: Make sure Terminal/iTerm has permission to access your Photos library in System Preferences > Privacy & Security > Photos.

**No Locations Found**: Ensure your photos have GPS metadata. Photos taken with GPS-enabled devices (iPhones, most modern cameras) will have this data.

**Database Access Issues**: If you have multiple Photos libraries, you may need to specify the database path using `--photos-db`.

## License

MIT License - feel free to use and modify!

## Credits

Built using [osxphotos](https://github.com/RhetTbull/osxphotos) by RhetTbull.

