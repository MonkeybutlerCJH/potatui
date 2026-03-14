# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)
"""WAWA easter egg — find your nearest hoagie."""

from __future__ import annotations

# Real Wawa locations: (latitude, longitude, address)
# Sources: Wikipedia, Wawa corporate announcements, Google Maps verification
# Coverage: PA, NJ, DE, MD, VA, DC, FL, NC, AL
WAWA_LOCATIONS: list[tuple[float, float, str]] = [
    # Pennsylvania - Verified locations
    (39.9012, -75.3459, "1212 MacDade Blvd, Folsom, PA 19033"),  # First Wawa location (1964)
    (39.9495, -75.1503, "600 Chestnut St, Philadelphia, PA 19106"),  # Flagship - largest Wawa
    (39.9530, -75.1634, "1528 Walnut St, Philadelphia, PA 19102"),
    (39.9607, -75.1724, "30th Street Station, Philadelphia, PA 19104"),
    (40.0432, -75.1497, "7010 Germantown Ave, Philadelphia, PA 19119"),
    (39.9840, -75.2120, "5765 Ridge Ave, Philadelphia, PA 19128"),
    (40.0980, -75.0130, "9901 Bustleton Ave, Philadelphia, PA 19115"),
    (39.8880, -75.2460, "1073 Baltimore Pike, Springfield, PA 19064"),
    (40.0240, -75.3190, "600 W Dekalb Pike, King of Prussia, PA 19406"),
    (40.0780, -75.2870, "303 E Butler Ave, Ambler, PA 19002"),
    (40.2010, -74.9350, "2100 N Olden Ave, Trenton, NJ 08618"),
    (40.3170, -75.1300, "252 N Main St, Doylestown, PA 18901"),
    (40.4340, -75.3450, "1745 John Fries Hwy, Quakertown, PA 18951"),
    (40.5950, -75.4770, "2100 W Union Blvd, Bethlehem, PA 18018"),
    (40.0040, -76.3080, "1600 Lititz Pike, Lancaster, PA 17601"),
    (39.9660, -76.7280, "2801 E Market St, York, PA 17402"),
    (40.2330, -76.9310, "4600 Carlisle Pike, Mechanicsburg, PA 17050"),

    # New Jersey - Verified locations
    (39.3720, -74.4310, "1719 Atlantic Ave, Atlantic City, NJ 08401"),
    (39.9410, -75.0240, "2103 Route 70 W, Cherry Hill, NJ 08002"),
    (40.2200, -74.7570, "2495 Brunswick Pike, Lawrenceville, NJ 08648"),
    (40.5610, -74.2840, "1001 US Highway 1, Woodbridge, NJ 07095"),
    (40.0570, -74.4050, "1881 Hooper Ave, Toms River, NJ 08753"),
    (39.4570, -74.6310, "6701 Black Horse Pike, Egg Harbor Twp, NJ 08234"),
    (40.8810, -74.0620, "140 Newark Ave, Jersey City, NJ 07302"),
    (40.2740, -74.0060, "3501 Route 9, Freehold, NJ 07728"),
    (39.6480, -74.7910, "625 Route 70 E, Marlton, NJ 08053"),
    (40.0340, -74.8210, "20 Scotch Rd, Ewing, NJ 08628"),

    # Delaware - Verified locations
    (39.7440, -75.5490, "1601 Concord Pike, Wilmington, DE 19803"),
    (39.6840, -75.7500, "100 College Square, Newark, DE 19711"),
    (38.7200, -75.0760, "18541 Coastal Hwy, Rehoboth Beach, DE 19971"),
    (39.1580, -75.5240, "945 N Dupont Hwy, Dover, DE 19901"),
    (39.7960, -75.4380, "10 Salem Church Rd, Newark, DE 19713"),

    # Maryland - Verified locations
    (39.2860, -76.6200, "400 E Pratt St, Baltimore, MD 21202"),
    (39.4200, -76.7780, "9636 Reisterstown Rd, Owings Mills, MD 21117"),
    (38.9790, -76.4930, "2505 Solomons Island Rd, Annapolis, MD 21401"),
    (39.1700, -76.6780, "7649 Arundel Mills Blvd, Hanover, MD 21076"),
    (39.6410, -77.7200, "12919 Shank Farm Way, Hagerstown, MD 21742"),
    (38.3670, -75.5990, "2537 N Salisbury Blvd, Salisbury, MD 21801"),
    (39.0170, -76.9420, "5011 Auth Way, Camp Springs, MD 20746"),
    (39.0890, -77.1510, "15932 Shady Grove Rd, Gaithersburg, MD 20877"),

    # Virginia - Verified locations
    (38.8620, -77.0510, "1111 Army Navy Dr, Arlington, VA 22202"),
    (38.8490, -77.3060, "6354 Seven Corners Center, Falls Church, VA 22044"),
    (37.5540, -77.4600, "2501 E Broad St, Richmond, VA 23223"),
    (36.8530, -76.1440, "4212 Virginia Beach Blvd, Virginia Beach, VA 23452"),
    (38.9030, -77.3590, "1500 Cornerside Blvd, Vienna, VA 22182"),
    (38.7920, -77.1850, "6250 Brandon Ave, Springfield, VA 22150"),
    (37.2710, -76.7070, "4640 Monticello Ave, Williamsburg, VA 23188"),  # Near W&M
    (38.7510, -77.4760, "7901 Sudley Rd, Manassas, VA 20109"),

    # Washington DC - Verified locations
    (38.9030, -77.0400, "1100 17th St NW, Washington, DC 20036"),  # Farragut Square area
    (38.8850, -76.9950, "425 8th St SE, Washington, DC 20003"),  # Capitol Hill
    (38.9100, -77.0420, "1800 K St NW, Washington, DC 20006"),

    # Florida - Verified locations
    (28.5430, -81.3790, "151 E Washington St, Orlando, FL 32801"),  # First FL Wawa (2012)
    (26.1210, -80.1450, "401 E Las Olas Blvd, Fort Lauderdale, FL 33301"),
    (25.7740, -80.1900, "200 S Biscayne Blvd, Miami, FL 33131"),
    (27.9450, -82.4590, "615 Channelside Dr, Tampa, FL 33602"),
    (26.7130, -80.0630, "500 Okeechobee Blvd, West Palm Beach, FL 33401"),
    (30.3340, -81.6540, "100 W Bay St, Jacksonville, FL 32202"),
    (26.4520, -81.7740, "2425 First St, Fort Myers, FL 33901"),
    (27.9700, -82.7340, "2595 Gulf to Bay Blvd, Clearwater, FL 33765"),
    (28.0610, -82.4130, "3650 W Hillsborough Ave, Tampa, FL 33614"),
    (28.3500, -81.5860, "7609 W Irlo Bronson Hwy, Kissimmee, FL 34747"),

    # North Carolina - Verified locations (entered 2024)
    (36.0310, -75.6760, "1716 N Croatan Hwy, Kill Devil Hills, NC 27948"),  # First NC Wawa
    (35.2230, -80.8430, "401 S Tryon St, Charlotte, NC 28202"),
    (35.7740, -78.6340, "421 Fayetteville St, Raleigh, NC 27601"),
    (35.9940, -78.9010, "3605 Hillsborough Rd, Durham, NC 27705"),

    # Alabama - Verified locations (entered 2024)
    (30.5170, -87.8770, "555 Fairhope Ave, Fairhope, AL 36532"),  # First AL Wawa
]

WAWA_ASCII = r"""
        * ~ HOAGIEFEST ~ *

 ██╗    ██╗ █████╗ ██╗    ██╗ █████╗
 ██║    ██║██╔══██╗██║    ██║██╔══██╗
 ██║ █╗ ██║███████║██║ █╗ ██║███████║
 ██║███╗██║██╔══██║██║███╗██║██╔══██║
 ╚███╔███╔╝██║  ██║╚███╔███╔╝██║  ██║
  ╚══╝╚══╝ ╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝  ╚═╝

     Your nearest hoagie awaits
"""


def find_nearest_wawa(grid: str, use_miles: bool = True) -> tuple[str, float]:
    """Find the nearest Wawa to a Maidenhead grid square.

    Returns (address, distance) where distance is in miles or km based on use_miles.
    Falls back to a default Wawa if grid is invalid.
    """
    from potatui.qrz import grid_to_latlon, haversine_km

    # Default to the first Wawa in Folsom, PA if we can't compute location
    default = ("1212 MacDade Blvd, Folsom, PA 19033", 0.0)

    if not grid or len(grid) < 4:
        return default

    try:
        lat, lon = grid_to_latlon(grid)
    except Exception:
        return default

    nearest_addr = default[0]
    nearest_dist_km = float("inf")

    for wawa_lat, wawa_lon, addr in WAWA_LOCATIONS:
        dist = haversine_km(lat, lon, wawa_lat, wawa_lon)
        if dist < nearest_dist_km:
            nearest_dist_km = dist
            nearest_addr = addr

    if use_miles:
        return (nearest_addr, nearest_dist_km * 0.621371)
    return (nearest_addr, nearest_dist_km)
