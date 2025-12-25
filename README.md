# GeoMemo - Personal GeoGuessr Map Creator

A fun project that extracts location data from your Apple Photos library and creates a personal GeoGuessr map!

## Features

- 📍 Extracts GPS coordinates from all photos and videos in your Apple Photos library
- 📊 Exports location data to CSV (for GeoGuessr) and GeoJSON (for visualization)
- 📈 Provides statistics about your photo locations
- 🎯 Ready-to-use for creating custom GeoGuessr maps
- 🔍 Filters out screenshots and non-camera media
- 📅 Optional date range filtering
- 🔄 Distance-based deduplication to avoid duplicate locations
- 🗺️ Optional Street View panorama validation (ensures locations work in GeoGuessr)
- 📊 Progress bars for all operations

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

4. (Optional) Create a `.env` file for your Google Maps API key:
```bash
echo "MAP_API_KEY=your_google_api_key_here" > .env
```

   This is only needed if you want to use `--filter-panos` to validate Street View coverage.

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

# Remove duplicate locations (distance-based, default 200m)
python location_extractor.py --dedupe --csv locations.csv

# Custom deduplication distance (e.g., 50m for more aggressive deduplication)
python location_extractor.py --dedupe --dedupe-distance 50 --csv locations.csv

# Filter locations to only include those with Street View panoramas
# Requires MAP_API_KEY in .env file
python location_extractor.py --filter-panos --csv locations.csv

# Custom panorama distance threshold (default: 200m)
python location_extractor.py --filter-panos --pano-max-distance 150 --csv locations.csv

# Test with limited API calls (check only first 10 locations)
python location_extractor.py --filter-panos --api-limit 10 --csv locations.csv

# Use a specific Photos library database
python location_extractor.py --photos-db /path/to/Photos.sqlite --csv locations.csv

# Combine multiple options (recommended for best results)
python location_extractor.py \
  --start-from 2020-01-01 \
  --end-on 2023-12-31 \
  --dedupe --dedupe-distance 200 \
  --filter-panos --pano-max-distance 40 \
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
| `--dedupe` | Remove duplicate locations within 200 meters (default distance) |
| `--dedupe-distance N` | Custom deduplication distance in meters (default: 200m when --dedupe is used) |
| `--filter-panos` | Filter locations to only include those with Street View panoramas (requires MAP_API_KEY) |
| `--pano-max-distance N` | Maximum distance in meters between photo and panorama (default: 200m) |
| `--api-limit N` | Limit number of locations to check for Street View panoramas (for testing). Only applies when `--filter-panos` is used |
| `--photos-db PATH` | Path to Photos library database (uses default if not specified) |

### Using the Module Directly

You can also use the `LocationExtractor` class in your own scripts:

```python
from location_extractor import LocationExtractor
import os
from dotenv import load_dotenv

load_dotenv()  # Load MAP_API_KEY from .env

# Initialize extractor
extractor = LocationExtractor()

# Extract locations with date filtering
locations = extractor.extract_locations(
    start_date='2020-01-01',
    end_date='2023-12-31'
)

# Deduplicate locations (distance-based, 200m default)
locations = extractor.deduplicate_locations(locations, distance_meters=200)

# Filter for Street View panoramas (optional)
api_key = os.environ.get('MAP_API_KEY')
if api_key:
    locations, filtered_count = extractor.filter_street_view_panos(
        locations,
        api_key=api_key,
        max_distance_m=40.0
    )

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

- The first run may take a while if you have a large Photos library (progress bars show progress)
- Only photos/videos with GPS coordinates will be included
- Photos with coordinates (0, 0) or null coordinates are automatically excluded
- Invalid coordinates (outside -90 to 90 lat, -180 to 180 lon) are filtered out
- Screenshots and imported media without camera EXIF data are filtered out
- Photos without dates are excluded when using date range filtering
- Region information comes from Apple Photos metadata (if available), otherwise set to "Unknown"
- Deduplication uses distance-based matching (Haversine formula) - locations within the specified distance are considered duplicates
- When using `--filter-panos`, exported coordinates use the actual Street View panorama location (not the photo location) for maximum GeoGuessr compatibility
- Progress bars are shown for photo processing, deduplication, and panorama checking

## Troubleshooting

**Permission Errors**: Make sure Terminal/iTerm has permission to access your Photos library in System Preferences > Privacy & Security > Photos.

**No Locations Found**: Ensure your photos have GPS metadata. Photos taken with GPS-enabled devices (iPhones, most modern cameras) will have this data.

**Database Access Issues**: If you have multiple Photos libraries, you may need to specify the database path using `--photos-db`.

**MAP_API_KEY Not Found**: If using `--filter-panos`, make sure you have a `.env` file in the project root with `MAP_API_KEY=your_key_here`, or set it as an environment variable.

**API Authorization Error ("This API project is not authorized to use this API")**: 
- Go to [Google Cloud Console API Library](https://console.cloud.google.com/apis/library)
- Search for "Street View Static API"
- Click "Enable"
- Wait a few minutes for changes to propagate
- Make sure billing is enabled (free tier available with $200/month credit)
- Verify your API key has the correct restrictions (or no restrictions for testing)

**Failed to Load Location in GeoGuessr**: 
- Use `--filter-panos` to validate Street View coverage before export
- Locations without nearby Street View panoramas will be filtered out
- The script uses panorama coordinates (not photo coordinates) for maximum compatibility

**Getting a Google Maps API Key**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select an existing one
3. Enable "Street View Static API"
4. Create credentials (API key)
5. Add it to your `.env` file as `MAP_API_KEY=your_key_here`

## License

MIT License - feel free to use and modify!

## Credits

Built using [osxphotos](https://github.com/RhetTbull/osxphotos) by RhetTbull.

