"""WAWA easter egg — find your nearest hoagie."""

from __future__ import annotations

from typing import Optional

# Wawa locations: (latitude, longitude, address)
# Curated selection across Wawa's footprint: PA, NJ, DE, MD, VA, DC, FL, NC
WAWA_LOCATIONS: list[tuple[float, float, str]] = [
    # Pennsylvania
    (39.9526, -75.1652, "1501 Market St, Philadelphia, PA 19102"),
    (40.0379, -75.1308, "7201 Germantown Ave, Philadelphia, PA 19119"),
    (39.9484, -75.1720, "1900 Chestnut St, Philadelphia, PA 19103"),
    (40.0021, -75.1180, "6301 Rising Sun Ave, Philadelphia, PA 19111"),
    (39.8651, -75.3528, "1101 W Baltimore Pike, Media, PA 19063"),
    (40.2454, -75.6494, "701 E Main St, Norristown, PA 19401"),
    (40.1084, -75.2932, "1300 Bethlehem Pike, Flourtown, PA 19031"),
    (40.0859, -74.8548, "1876 N Olden Ave, Ewing, NJ 08618"),
    (40.3131, -75.1306, "199 N Main St, Doylestown, PA 18901"),
    (40.5954, -75.4757, "2160 W Union Blvd, Bethlehem, PA 18018"),
    (40.3340, -75.9269, "2925 N Reading Rd, Adamstown, PA 19501"),
    (40.0088, -76.3058, "1759 Columbia Ave, Lancaster, PA 17603"),
    (39.9656, -76.7275, "2550 E Market St, York, PA 17402"),
    (40.2737, -76.8867, "3401 Hartzdale Dr, Camp Hill, PA 17011"),
    
    # New Jersey
    (39.3643, -74.4229, "2400 Atlantic Ave, Atlantic City, NJ 08401"),
    (39.9285, -74.9658, "1809 Rt 38, Cherry Hill, NJ 08002"),
    (40.2171, -74.7429, "3349 US-1, Lawrenceville, NJ 08648"),
    (40.4862, -74.4518, "335 US-9, Woodbridge, NJ 07095"),
    (40.7282, -74.0776, "95 Montgomery St, Jersey City, NJ 07302"),
    (40.0583, -74.4057, "2100 Route 37, Toms River, NJ 08753"),
    (39.4519, -74.6329, "6701 Black Horse Pike, Egg Harbor Twp, NJ 08234"),
    (40.8568, -74.2263, "490 Broad St, Newark, NJ 07102"),
    (39.8868, -75.0241, "601 N Kings Hwy, Cherry Hill, NJ 08034"),
    (40.6340, -74.2107, "1350 US-22, Mountainside, NJ 07092"),
    
    # Delaware
    (39.7391, -75.5398, "1601 Concord Pike, Wilmington, DE 19803"),
    (39.6780, -75.7506, "101 E Main St, Newark, DE 19711"),
    (38.9108, -75.5277, "18541 Coastal Hwy, Rehoboth Beach, DE 19971"),
    (39.1582, -75.5244, "953 N Dupont Hwy, Dover, DE 19901"),
    (38.7788, -75.1594, "36844 Lighthouse Rd, Selbyville, DE 19975"),
    
    # Maryland
    (39.2904, -76.6122, "400 E Pratt St, Baltimore, MD 21202"),
    (39.4143, -76.7792, "9616 Reisterstown Rd, Owings Mills, MD 21117"),
    (38.9784, -76.4922, "2505 Solomons Island Rd, Annapolis, MD 21401"),
    (39.0458, -76.6413, "7649 Arundel Mills Blvd, Hanover, MD 21076"),
    (39.6418, -77.7200, "12919 Shank Farm Way, Hagerstown, MD 21742"),
    (38.3607, -75.5994, "2514 N Salisbury Blvd, Salisbury, MD 21801"),
    (38.9695, -77.0257, "5011 Rhode Island Ave, Hyattsville, MD 20781"),
    
    # Virginia
    (38.8816, -77.0910, "1111 Army Navy Dr, Arlington, VA 22202"),
    (38.8462, -77.3064, "6355 Seven Corners Ctr, Falls Church, VA 22044"),
    (37.5407, -77.4360, "2501 E Broad St, Richmond, VA 23223"),
    (36.8529, -75.9780, "4429 Virginia Beach Blvd, Virginia Beach, VA 23462"),
    (38.9581, -77.3590, "1929 Chain Bridge Rd, McLean, VA 22102"),
    (37.3211, -79.9414, "4406 Brambleton Ave SW, Roanoke, VA 24018"),
    (38.7516, -77.4753, "7901 Sudley Rd, Manassas, VA 20109"),
    (39.1910, -78.1647, "150 Kernstown Commons Blvd, Winchester, VA 22602"),
    
    # Washington DC
    (38.9072, -77.0369, "1100 15th St NW, Washington, DC 20005"),
    (38.8951, -77.0364, "425 8th St SE, Washington, DC 20003"),
    (38.9170, -77.0223, "2300 N St NW, Washington, DC 20037"),
    
    # Florida
    (26.1224, -80.1373, "401 E Las Olas Blvd, Fort Lauderdale, FL 33301"),
    (25.7617, -80.1918, "200 S Biscayne Blvd, Miami, FL 33131"),
    (28.5383, -81.3792, "151 E Washington St, Orlando, FL 32801"),
    (27.9506, -82.4572, "615 Channelside Dr, Tampa, FL 33602"),
    (26.7153, -80.0534, "500 S Rosemary Ave, West Palm Beach, FL 33401"),
    (30.3322, -81.6557, "100 N Laura St, Jacksonville, FL 32202"),
    (26.6406, -81.8723, "2301 First St, Fort Myers, FL 33901"),
    (27.3364, -82.5307, "1819 Main St, Sarasota, FL 34236"),
    
    # North Carolina
    (35.2271, -80.8431, "401 S Tryon St, Charlotte, NC 28202"),
    (35.7796, -78.6382, "421 Fayetteville St, Raleigh, NC 27601"),
    (35.9132, -79.0558, "201 W Main St, Durham, NC 27701"),
    (36.0726, -79.7920, "120 E Market St, Greensboro, NC 27401"),
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
    
    # Default to the OG Wawa in Philly if we can't compute location
    default = ("1501 Market St, Philadelphia, PA 19102", 0.0)
    
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
