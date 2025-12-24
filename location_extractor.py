"""
Location Extractor Module

Extracts location data from Apple Photos library using osxphotos.
Exports location data to CSV and GeoJSON formats for GeoGuessr map creation.
"""

import csv
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from datetime import datetime
import osxphotos


class LocationExtractor:
    """Extract location data from Apple Photos library."""
    
    def __init__(self, photos_db_path: Optional[str] = None):
        """
        Initialize the location extractor.
        
        Args:
            photos_db_path: Optional path to Photos library database.
                           If None, uses default Photos library.
        """
        if photos_db_path:
            self.photosdb = osxphotos.PhotosDB(photos_db_path)
        else:
            self.photosdb = osxphotos.PhotosDB()
    
    def _is_valid_camera_media(self, photo) -> bool:
        """
        Check if photo/video was taken with a real camera device.
        Filters out screenshots and imported media without camera info.
        
        Args:
            photo: PhotoInfo object from osxphotos
            
        Returns:
            True if media appears to be from a camera device, False otherwise
        """
        # Check for EXIF camera information
        if hasattr(photo, 'exif_info') and photo.exif_info:
            exif = photo.exif_info
            # Check if camera make/model are available
            camera_make = getattr(exif, 'camera_make', None)
            camera_model = getattr(exif, 'camera_model', None)
            
            # If both make and model are missing/empty, likely a screenshot or imported media
            if not camera_make and not camera_model:
                return False
            
            # If we have camera info, it's likely from a real camera
            return True
        
        # If no exif_info attribute or it's None, likely a screenshot
        return False
    
    def deduplicate_locations(self, locations: List[Dict], precision: int = 6) -> List[Dict]:
        """
        Remove duplicate locations based on rounded coordinates.
        
        Args:
            locations: List of location dictionaries
            precision: Number of decimal places to round coordinates to (default: 6, ~0.1m precision)
            
        Returns:
            Deduplicated list of location dictionaries
        """
        seen = set()
        deduplicated = []
        
        for loc in locations:
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            
            if lat is None or lon is None:
                continue
            
            # Round coordinates to specified precision
            rounded_lat = round(lat, precision)
            rounded_lon = round(lon, precision)
            
            # Create a key for this location
            location_key = (rounded_lat, rounded_lon)
            
            # Only add if we haven't seen this location before
            if location_key not in seen:
                seen.add(location_key)
                deduplicated.append(loc)
        
        return deduplicated
    
    def extract_locations(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
        """
        Extract location data from all photos with GPS coordinates.
        Filters out screenshots and non-camera media.
        
        Args:
            start_date: Start date in YYYY-MM-DD format (inclusive). If None, no start filter.
            end_date: End date in YYYY-MM-DD format (inclusive). If None, no end filter.
        
        Returns:
            List of dictionaries containing photo location data
        """
        photos_with_location = []
        skipped_count = 0
        null_coord_count = 0
        date_filtered_count = 0
        
        # Helper function to normalize datetimes to timezone-naive for comparison
        def normalize_datetime(dt):
            """Convert timezone-aware datetime to naive datetime."""
            if dt is None:
                return None
            if dt.tzinfo is not None:
                # Remove timezone info for comparison
                return dt.replace(tzinfo=None)
            return dt
        
        # Parse date strings if provided
        start_datetime = None
        end_datetime = None
        
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                raise ValueError(f"Invalid start_date format: {start_date}. Expected YYYY-MM-DD")
        
        if end_date:
            try:
                # Set end_date to end of day for inclusive comparison
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            except ValueError:
                raise ValueError(f"Invalid end_date format: {end_date}. Expected YYYY-MM-DD")
        
        if start_datetime and end_datetime and start_datetime > end_datetime:
            raise ValueError("start_date must be before or equal to end_date")
        
        # Normalize parsed datetimes (they're already naive, but ensure consistency)
        start_datetime = normalize_datetime(start_datetime)
        end_datetime = normalize_datetime(end_datetime)
        
        print("Scanning Photos library...")
        if start_date or end_date:
            date_range_str = f" (date range: {start_date or 'any'} to {end_date or 'any'})"
            print(f"Filtering by date range{date_range_str}...")
        
        all_photos = self.photosdb.photos()
        total_photos = len(all_photos)
        
        for idx, photo in enumerate(all_photos, 1):
            if idx % 1000 == 0:
                print(f"  Processed {idx}/{total_photos} photos...")
            
            # Check if photo has location data
            if photo.location:
                lat, lon = photo.location
                
                # Skip if coordinates are null/None
                if lat is None or lon is None:
                    null_coord_count += 1
                    continue
                
                # Skip if coordinates are invalid (0, 0 is often a default/error value)
                if lat != 0.0 or lon != 0.0:
                    # Filter by date range if specified
                    if photo.date:
                        photo_datetime = normalize_datetime(photo.date)
                        if start_datetime and photo_datetime < start_datetime:
                            date_filtered_count += 1
                            continue
                        if end_datetime and photo_datetime > end_datetime:
                            date_filtered_count += 1
                            continue
                    elif (start_datetime or end_datetime):
                        # If date filtering is requested but photo has no date, skip it
                        date_filtered_count += 1
                        continue
                    
                    # Filter out screenshots and non-camera media
                    if not self._is_valid_camera_media(photo):
                        skipped_count += 1
                        continue
                    
                    # Try to get place/region info from photo metadata if available
                    region = None
                    
                    # Check if osxphotos provides place information
                    # Apple Photos stores reverse geocoded place names
                    if hasattr(photo, 'place') and photo.place:
                        # Try accessing region attribute if place is an object
                        if hasattr(photo.place, 'country'):
                            region = photo.place.country
                        elif hasattr(photo.place, 'name'):
                            # Sometimes place.name contains the full location string
                            place_name = photo.place.name
                            # Try to extract region if it's in a structured format
                            if isinstance(place_name, str) and ',' in place_name:
                                # Might be "City, State, Country" format
                                parts = [p.strip() for p in place_name.split(',')]
                                if len(parts) > 0:
                                    region = parts[-1]
                    
                    # Use "Unknown" if region not available
                    if not region:
                        region = 'Unknown'
                    
                    photo_data = {
                        'uuid': photo.uuid,
                        'filename': photo.original_filename or 'Unknown',
                        'title': photo.title or photo.original_filename or 'Untitled',
                        'description': photo.description or '',
                        'latitude': lat,
                        'longitude': lon,
                        'date': photo.date.isoformat() if photo.date else '',
                        'is_video': photo.ismovie,
                        'is_favorite': photo.favorite,
                        'region': region,
                    }
                    photos_with_location.append(photo_data)
        
        print(f"\nFound {len(photos_with_location)} photos/videos with location data")
        if skipped_count > 0:
            print(f"Skipped {skipped_count} screenshots/non-camera media")
        if null_coord_count > 0:
            print(f"Skipped {null_coord_count} photos/videos with null coordinates")
        if date_filtered_count > 0:
            print(f"Skipped {date_filtered_count} photos/videos outside date range")
        return photos_with_location
    
    def export_to_csv(self, locations: List[Dict], output_path: str = 'photo_locations.csv'):
        """
        Export location data to CSV file (GeoGuessr format).
        
        Args:
            locations: List of location dictionaries
            output_path: Path to output CSV file
        """
        output_file = Path(output_path)
        
        # Filter out any null coordinates as a safety check
        valid_locations = [
            loc for loc in locations 
            if loc.get('latitude') is not None 
            and loc.get('longitude') is not None
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Latitude', 'Longitude'])
            for loc in valid_locations:
                writer.writerow([loc['latitude'], loc['longitude']])
        
        filtered_count = len(locations) - len(valid_locations)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} entries with null coordinates from CSV")
        print(f"CSV file saved to: {output_file.absolute()}")
    
    def export_to_geojson(self, locations: List[Dict], output_path: str = 'photo_locations.geojson'):
        """
        Export location data to GeoJSON file, grouped by region.
        
        Args:
            locations: List of location dictionaries
            output_path: Path to output GeoJSON file
        """
        output_file = Path(output_path)
        
        if not locations:
            # Create empty FeatureCollection
            geojson = {
                "type": "FeatureCollection",
                "features": []
            }
            with open(output_file, 'w', encoding='utf-8') as geojsonfile:
                json.dump(geojson, geojsonfile, indent=2, ensure_ascii=False)
            print(f"GeoJSON file saved to: {output_file.absolute()}")
            return
        
        # Filter out any null coordinates as a safety check
        valid_locations = [
            loc for loc in locations 
            if loc.get('latitude') is not None 
            and loc.get('longitude') is not None
        ]
        
        filtered_count = len(locations) - len(valid_locations)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} entries with null coordinates from GeoJSON")
        
        # Group coordinates by region
        print("Grouping coordinates by region...")
        region_coords = defaultdict(list)
        
        for loc in valid_locations:
            region = loc.get('region', 'Unknown')
            region_coords[region].append([loc['longitude'], loc['latitude']])
        
        print(f"Found {len(region_coords)} regions")
        
        # Create features for each region
        features = []
        for region, coordinates in sorted(region_coords.items()):
            feature = {
                "type": "Feature",
                "properties": {
                    "region": region
                },
                "geometry": {
                    "type": "MultiPoint",
                    "coordinates": coordinates
                }
            }
            features.append(feature)
        
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        with open(output_file, 'w', encoding='utf-8') as geojsonfile:
            json.dump(geojson, geojsonfile, indent=2, ensure_ascii=False)
        
        print(f"GeoJSON file saved to: {output_file.absolute()}")
    
    def get_statistics(self, locations: List[Dict]) -> Dict:
        """
        Get statistics about extracted locations.
        
        Args:
            locations: List of location dictionaries
            
        Returns:
            Dictionary with statistics
        """
        if not locations:
            return {
                'total': 0,
                'photos': 0,
                'videos': 0,
                'favorites': 0,
                'with_description': 0,
                'null_coordinates': 0,
            }
        
        # Filter out null coordinates for valid stats
        valid_locations = [
            loc for loc in locations 
            if loc.get('latitude') is not None 
            and loc.get('longitude') is not None
        ]
        null_coord_count = len(locations) - len(valid_locations)
        
        stats = {
            'total': len(valid_locations),
            'photos': sum(1 for loc in valid_locations if not loc['is_video']),
            'videos': sum(1 for loc in valid_locations if loc['is_video']),
            'favorites': sum(1 for loc in valid_locations if loc['is_favorite']),
            'with_description': sum(1 for loc in valid_locations if loc['description']),
            'null_coordinates': null_coord_count,
        }
        
        # Calculate date range
        dates = [loc['date'] for loc in valid_locations if loc['date']]
        if dates:
            dates.sort()
            stats['date_range'] = {
                'earliest': dates[0],
                'latest': dates[-1],
            }
        
        return stats


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Extract location data from Apple Photos library'
    )
    parser.add_argument(
        '--photos-db',
        type=str,
        help='Path to Photos library database (optional, uses default if not specified)'
    )
    parser.add_argument(
        '--csv',
        type=str,
        default='',
        help='Output CSV file path. If not provided, CSV will not be exported.'
    )
    parser.add_argument(
        '--geojson',
        type=str,
        default='',
        help='Output GeoJSON file path. If not provided, GeoJSON will not be exported.'
    )
    parser.add_argument(
        '--start-from',
        type=str,
        default='',
        help='Start date in YYYY-MM-DD format (inclusive). If empty, no start filter.'
    )
    parser.add_argument(
        '--end-on',
        type=str,
        default='',
        help='End date in YYYY-MM-DD format (inclusive). If empty, no end filter.'
    )
    parser.add_argument(
        '--dedupe',
        action='store_true',
        help='Remove duplicate locations (same coordinates rounded to 6 decimal places, ~0.1m precision)'
    )
    parser.add_argument(
        '--dedupe-precision',
        type=int,
        default=6,
        help='Precision for deduplication (decimal places). Default: 6 (~0.1m). Lower = more aggressive deduplication.'
    )
    
    args = parser.parse_args()
    
    # Initialize extractor
    extractor = LocationExtractor(photos_db_path=args.photos_db)
    
    # Parse date arguments (empty string means None)
    start_date = args.start_from if args.start_from else None
    end_date = args.end_on if args.end_on else None
    
    # Extract locations
    locations = extractor.extract_locations(start_date=start_date, end_date=end_date)
    
    # Deduplicate if requested
    original_count = len(locations)
    dedupe_count = 0
    if args.dedupe:
        locations = extractor.deduplicate_locations(locations, precision=args.dedupe_precision)
        dedupe_count = original_count - len(locations)
        if dedupe_count > 0:
            print(f"\nDeduplicated: removed {dedupe_count} duplicate locations ({len(locations)} unique locations remaining)")
    
    # Show statistics
    stats = extractor.get_statistics(locations)
    print("\n" + "="*50)
    print("STATISTICS")
    print("="*50)
    print(f"Total photos/videos with location: {stats['total']}")
    print(f"  - Photos: {stats['photos']}")
    print(f"  - Videos: {stats['videos']}")
    print(f"  - Favorites: {stats['favorites']}")
    print(f"  - With description: {stats['with_description']}")
    if stats.get('null_coordinates', 0) > 0:
        print(f"  - Null coordinates filtered: {stats['null_coordinates']}")
    if dedupe_count > 0:
        print(f"  - Duplicates removed: {dedupe_count}")
    if 'date_range' in stats:
        print(f"\nDate range:")
        print(f"  - Earliest: {stats['date_range']['earliest']}")
        print(f"  - Latest: {stats['date_range']['latest']}")
    print("="*50 + "\n")
    
    # Export files only if output paths are provided
    exported_any = False
    if args.csv:
        extractor.export_to_csv(locations, args.csv)
        exported_any = True
    if args.geojson:
        extractor.export_to_geojson(locations, args.geojson)
        exported_any = True
    
    if exported_any:
        print("\n✓ Export complete!")
    else:
        print("\nNo output files specified. Use --csv and/or --geojson to export files.")


if __name__ == '__main__':
    main()

