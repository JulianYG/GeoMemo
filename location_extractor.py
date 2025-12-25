"""
Location Extractor Module

Extracts location data from Apple Photos library using osxphotos.
Exports location data to CSV and GeoJSON formats for GeoGuessr map creation.

Note on GeoGuessr Coverage:
GeoGuessr handles locations without Street View coverage by finding the nearest
available Street View location or using satellite/aerial imagery as a fallback.
However, some locations may still fail to load if:
- The location is in a remote area with no nearby Street View coverage
- The coordinates are in oceans or areas completely without imagery
- There are temporary API issues

The extractor validates coordinates to ensure they're within valid ranges (-90 to 90
for latitude, -180 to 180 for longitude) and filters out obviously invalid coordinates
like (0, 0). If you still encounter "failed to load location" errors, those locations
likely don't have any nearby Street View coverage and GeoGuessr cannot find a suitable
alternative. You may need to manually remove those locations from your CSV.
"""

import csv
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from datetime import datetime
import math
import os
import urllib.request
import urllib.error
import urllib.parse
import osxphotos
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


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
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points on Earth in meters.
        
        Args:
            lat1, lon1: Latitude and longitude of first point
            lat2, lon2: Latitude and longitude of second point
            
        Returns:
            Distance in meters
        """
        # Earth radius in meters
        R = 6371000
        
        # Convert to radians
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        # Haversine formula
        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def deduplicate_locations(self, locations: List[Dict], distance_meters: float = 200.0) -> List[Dict]:
        """
        Remove duplicate locations using distance-based deduplication (Haversine formula).
        
        Args:
            locations: List of location dictionaries
            distance_meters: Maximum distance in meters to consider locations as duplicates (default: 200m)
            
        Returns:
            Deduplicated list of location dictionaries (keeps the first occurrence of each duplicate)
        """
        deduplicated = []
        
        # Use tqdm for progress bar
        for loc in tqdm(locations, desc="Deduplicating locations", unit="location"):
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            
            if lat is None or lon is None:
                continue
            
            # Check if this location is within distance_meters of any already added location
            is_duplicate = False
            for existing_loc in deduplicated:
                existing_lat = existing_loc.get('latitude')
                existing_lon = existing_loc.get('longitude')
                
                if existing_lat is None or existing_lon is None:
                    continue
                
                distance = self._haversine_distance(lat, lon, existing_lat, existing_lon)
                if distance <= distance_meters:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated.append(loc)
        
        return deduplicated
    
    def _check_street_view_pano(self, lat: float, lon: float, api_key: str, radius: int = 50) -> Optional[Dict]:
        """
        Check if a Street View panorama exists near the given coordinates.
        Uses Google Street View Metadata API.
        
        Args:
            lat: Latitude
            lon: Longitude
            api_key: Google Maps API key
            radius: Search radius in meters (default: 50m)
            
        Returns:
            Dictionary with pano info if found, None otherwise.
            Format: {'pano_lat': float, 'pano_lon': float, 'pano_id': str, 'distance_m': float}
        """
        base_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
        
        params = {
            'location': f"{lat},{lon}",
            'radius': radius,
            'key': api_key
        }
        
        try:
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            request = urllib.request.Request(url)
            
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode())
                status = data.get('status', 'UNKNOWN_ERROR')
                
                if status == 'OK':
                    pano_location = data.get('location', {})
                    pano_lat = pano_location.get('lat')
                    pano_lon = pano_location.get('lng')
                    pano_id = data.get('pano_id', '')
                    
                    if pano_lat is not None and pano_lon is not None:
                        # Calculate distance between photo location and panorama location
                        distance_m = self._haversine_distance(lat, lon, pano_lat, pano_lon)
                        
                        return {
                            'pano_lat': pano_lat,
                            'pano_lon': pano_lon,
                            'pano_id': pano_id,
                            'distance_m': distance_m
                        }
                
                # No panorama found
                return None
                
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            # If API call fails, return None (fail closed - don't include location)
            return None
    
    def filter_street_view_panos(self, locations: List[Dict], api_key: str, max_distance_m: float = 40.0) -> Tuple[List[Dict], int]:
        """
        Filter locations to only include those with Street View panoramas within acceptable distance.
        
        Args:
            locations: List of location dictionaries
            api_key: Google Maps API key
            max_distance_m: Maximum distance in meters between photo and panorama (default: 40m)
                          Locations with distance > max_distance_m will be filtered out
            
        Returns:
            Tuple of (filtered_locations, filtered_count)
            Filtered locations will have pano_lat, pano_lon, pano_distance_m, and pano_id added to their dict
        """
        filtered = []
        filtered_count = 0
        
        print(f"Checking Street View panorama coverage (max distance: {max_distance_m}m)...")
        total = len(locations)
        
        # Use tqdm for progress bar
        for loc in tqdm(locations, total=total, desc="Checking panoramas", unit="location"):
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            
            if lat is None or lon is None:
                filtered_count += 1
                continue
            
            # Check for Street View panorama
            pano_info = self._check_street_view_pano(lat, lon, api_key, radius=50)
            
            if pano_info is None:
                # No panorama found
                filtered_count += 1
                continue
            
            distance_m = pano_info['distance_m']
            
            if distance_m > max_distance_m:
                # Panorama too far away
                filtered_count += 1
                continue
            
            # Add panorama info to location dict
            loc_with_pano = loc.copy()
            loc_with_pano['pano_lat'] = pano_info['pano_lat']
            loc_with_pano['pano_lon'] = pano_info['pano_lon']
            loc_with_pano['pano_distance_m'] = distance_m
            loc_with_pano['pano_id'] = pano_info.get('pano_id', '')
            
            filtered.append(loc_with_pano)
        
        return filtered, filtered_count
    
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
        
        # Use tqdm for progress bar
        for photo in tqdm(all_photos, total=total_photos, desc="Processing photos", unit="photo"):
            
            # Check if photo has location data
            if photo.location:
                lat, lon = photo.location
                
                # Skip if coordinates are null/None
                if lat is None or lon is None:
                    null_coord_count += 1
                    continue
                
                # Validate coordinate ranges
                # Latitude must be between -90 and 90
                # Longitude must be between -180 and 180
                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
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
        
        # Filter out any null or invalid coordinates as a safety check
        valid_locations = []
        for loc in locations:
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            
            if lat is None or lon is None:
                continue
            
            # Validate coordinate ranges
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                continue
            
            # Skip (0, 0) coordinates as they're often invalid
            if lat == 0.0 and lon == 0.0:
                continue
            
            valid_locations.append(loc)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Latitude', 'Longitude'])
            for loc in valid_locations:
                # Use panorama coordinates if available (for GeoGuessr), otherwise use photo coordinates
                lat = loc.get('pano_lat', loc.get('latitude'))
                lon = loc.get('pano_lon', loc.get('longitude'))
                writer.writerow([lat, lon])
        
        filtered_count = len(locations) - len(valid_locations)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} entries with invalid coordinates from CSV")
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
        
        # Filter out any null or invalid coordinates as a safety check
        valid_locations = []
        for loc in locations:
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            
            if lat is None or lon is None:
                continue
            
            # Validate coordinate ranges
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                continue
            
            # Skip (0, 0) coordinates as they're often invalid
            if lat == 0.0 and lon == 0.0:
                continue
            
            valid_locations.append(loc)
        
        filtered_count = len(locations) - len(valid_locations)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} entries with invalid coordinates from GeoJSON")
        
        # Group coordinates by region
        print("Grouping coordinates by region...")
        region_coords = defaultdict(list)
        
        for loc in valid_locations:
            region = loc.get('region', 'Unknown')
            # Use panorama coordinates if available (for GeoGuessr), otherwise use photo coordinates
            lon = loc.get('pano_lon', loc.get('longitude'))
            lat = loc.get('pano_lat', loc.get('latitude'))
            region_coords[region].append([lon, lat])
        
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
        
        # Filter out null or invalid coordinates for valid stats
        valid_locations = []
        for loc in locations:
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            
            if lat is None or lon is None:
                continue
            
            # Validate coordinate ranges
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                continue
            
            # Skip (0, 0) coordinates as they're often invalid
            if lat == 0.0 and lon == 0.0:
                continue
            
            valid_locations.append(loc)
        
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
        help='Remove duplicate locations within 200 meters of each other (default distance)'
    )
    parser.add_argument(
        '--dedupe-distance',
        type=float,
        default=500.0,
        help='Override default deduplication distance. Remove locations within this many meters of each other (default: 200m when --dedupe is used)'
    )
    parser.add_argument(
        '--filter-panos',
        action='store_true',
        help='Filter locations to only include those with Street View panoramas within acceptable distance (requires MAP_API_KEY in .env file)'
    )
    parser.add_argument(
        '--pano-max-distance',
        type=float,
        default=40.0,
        help='Maximum distance in meters between photo location and Street View panorama (default: 40m). Locations with distance > this will be filtered out.'
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
    pano_filtered_count = 0
    
    if args.dedupe:
        # Use custom distance if provided, otherwise default to 200m
        distance = args.dedupe_distance
        locations = extractor.deduplicate_locations(locations, distance_meters=distance)
        dedupe_count = original_count - len(locations)
        if dedupe_count > 0:
            print(f"\nDeduplicated ({distance}m): removed {dedupe_count} duplicate locations ({len(locations)} unique locations remaining)")
    
    # Filter Street View panoramas if requested
    if args.filter_panos:
        api_key = os.environ.get('MAP_API_KEY')
        if not api_key:
            print("\n⚠️  Warning: --filter-panos requires MAP_API_KEY in .env file or environment variable. Skipping panorama filtering.")
        else:
            locations, pano_filtered_count = extractor.filter_street_view_panos(
                locations,
                api_key=api_key,
                max_distance_m=args.pano_max_distance
            )
            if pano_filtered_count > 0:
                print(f"\nFiltered out {pano_filtered_count} locations without Street View panoramas or with panoramas too far away")
                print(f"({len(locations)} locations with valid panoramas remaining)")
            else:
                print(f"\nAll {len(locations)} locations have valid Street View panoramas")
    
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
    if pano_filtered_count > 0:
        print(f"  - No Street View panorama (or too far): {pano_filtered_count}")
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

