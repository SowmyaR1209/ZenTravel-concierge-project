from mcp.server.fastmcp import FastMCP
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zentravel-mcp-server")

# Create an MCP server named "ZenTravelTools"
mcp = FastMCP("ZenTravelTools")

@mcp.tool()
def get_weather(city: str) -> dict:
    """Get current weather forecast for a destination city.

    Args:
        city: The name of the city.
    """
    logger.info(f"get_weather called with city={city}")
    c = city.lower()
    if "tokyo" in c:
        return {"weather": "Rainy, 22°C, high humidity", "success": True}
    elif "paris" in c:
        return {"weather": "Sunny, 25°C, mild breeze", "success": True}
    elif "new york" in c:
        return {"weather": "Cloudy, 18°C, chance of rain", "success": True}
    return {"weather": "Mild, 20°C, clear skies", "success": True}

@mcp.tool()
def get_travel_advisory(country: str) -> dict:
    """Get travel advisory safety level and warnings for a country.

    Args:
        country: The name of the country.
    """
    logger.info(f"get_travel_advisory called with country={country}")
    c = country.lower()
    if "japan" in c:
        return {
            "country": country,
            "advisory_level": "LEVEL 1",
            "warning": "Exercise Normal Precautions.",
            "details": "Japan is generally very safe, but exercise standard safety measures.",
            "success": True
        }
    elif "syria" in c or "yemen" in c or "somalia" in c or "ukraine" in c or "afghanistan" in c:
        return {
            "country": country,
            "advisory_level": "LEVEL 4",
            "warning": "Do Not Travel.",
            "details": "Extreme threat of violence, terrorism, civil unrest, or active conflict. Do not travel to this region.",
            "success": True
        }
    elif "france" in c:
        return {
            "country": country,
            "advisory_level": "LEVEL 2",
            "warning": "Exercise Increased Caution.",
            "details": "Due to potential civil unrest, demonstrations, and street crime.",
            "success": True
        }
    elif "mexico" in c or "egypt" in c:
        return {
            "country": country,
            "advisory_level": "LEVEL 3",
            "warning": "Reconsider Travel.",
            "details": "High levels of crime, kidnapping, or risk. Reconsider travel plans to this area.",
            "success": True
        }
    return {
        "country": country,
        "advisory_level": "LEVEL 1",
        "warning": "Exercise Normal Precautions.",
        "details": "No active travel warnings for this region.",
        "success": True
    }

@mcp.tool()
def calculate_packing_essentials(weather_profile: str, duration_days: int) -> dict:
    """Calculate travel packing essentials based on weather and trip duration.

    Args:
        weather_profile: Typical weather profile (e.g. Rainy, Sunny, Snowy).
        duration_days: Length of the trip in days.
    """
    logger.info(f"calculate_packing_essentials called with weather={weather_profile}, duration={duration_days}")
    w = weather_profile.lower()
    items = ["Passport", "Toothbrush/Toiletries", "Chargers", "Underwear", "Socks"]
    
    # Add weather specific items
    if "rain" in w:
        items.extend(["Umbrella", "Raincoat", "Waterproof shoes"])
    elif "sun" in w or "hot" in w or "warm" in w:
        items.extend(["Sunglasses", "Sunscreen", "Swimwear", "Hat"])
    elif "snow" in w or "cold" in w:
        items.extend(["Heavy coat", "Gloves", "Scarf", "Thermal layers"])
    else:
        items.extend(["Light jacket", "Comfortable walking shoes"])
        
    # Calculate quantity of basic clothing
    shirt_count = min(duration_days, 10)
    pant_count = min(max(duration_days // 2, 2), 5)
    
    return {
        "packing_list": items,
        "recommended_shirts": shirt_count,
        "recommended_pants": pant_count,
        "success": True
    }

if __name__ == "__main__":
    mcp.run()
