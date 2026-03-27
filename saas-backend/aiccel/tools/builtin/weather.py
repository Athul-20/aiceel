# aiccel/tools_v2/builtin/weather.py
"""
Weather Tool - No Hardcoded APIs
=================================

Provides weather information via pluggable providers.
All endpoints and API configurations are fully customizable.

Usage:
    # Auto-configure from environment
    weather = WeatherTool()  # Uses WEATHER_PROVIDER, WEATHER_API_KEY

    # Explicit configuration
    weather = WeatherTool(
        provider="openweathermap",
        api_key="your-key",
        endpoint="https://custom.api.endpoint/weather"
    )
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Union

import requests

from ..base import (
    BaseTool,
    ParameterSchema,
    ParameterType,
    ToolConfigurationError,
    ToolExecutionError,
    ToolResult,
)


logger = logging.getLogger(__name__)


# =============================================================================
# WEATHER DATA STRUCTURES
# =============================================================================

@dataclass
class WeatherCondition:
    """Current weather condition"""
    description: str
    temperature: float
    feels_like: float
    humidity: int
    wind_speed: float
    clouds: Optional[int] = None
    rain_1h: Optional[float] = None
    snow_1h: Optional[float] = None


@dataclass
class ForecastPeriod:
    """A single forecast period"""
    time: str
    temperature: float
    condition: str


@dataclass
class WeatherResponse:
    """Complete weather response"""
    location: str
    country: str
    current: WeatherCondition
    forecast: list[ForecastPeriod] = field(default_factory=list)
    units: str = "imperial"

    def to_text(self) -> str:
        """Format as readable text"""
        unit = "°F" if self.units == "imperial" else "°C"
        speed_unit = "mph" if self.units == "imperial" else "m/s"

        parts = [
            f"Weather in {self.location}, {self.country}:",
            f"• Temperature: {self.current.temperature}{unit} (feels like {self.current.feels_like}{unit})",
            f"• Conditions: {self.current.description.capitalize()}",
            f"• Humidity: {self.current.humidity}%",
            f"• Wind Speed: {self.current.wind_speed} {speed_unit}"
        ]

        if self.current.clouds is not None:
            parts.append(f"• Cloud Cover: {self.current.clouds}%")
        if self.current.rain_1h is not None:
            parts.append(f"• Rainfall (last hour): {self.current.rain_1h} mm")
        if self.current.snow_1h is not None:
            parts.append(f"• Snowfall (last hour): {self.current.snow_1h} mm")

        if self.forecast:
            parts.append("\nForecast:")
            for period in self.forecast:
                parts.append(f"• {period.time}: {period.temperature}{unit}, {period.condition}")

        return "\n".join(parts)


# =============================================================================
# WEATHER PROVIDER INTERFACE
# =============================================================================

class WeatherProvider(ABC):
    """
    Abstract interface for weather providers.

    Implement this to add a new weather backend.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name"""
        pass

    @abstractmethod
    def get_weather(
        self,
        location: str,
        units: str = "imperial",
        include_forecast: bool = True
    ) -> WeatherResponse:
        """
        Get weather for a location.

        Args:
            location: City name or coordinates
            units: "imperial" or "metric"
            include_forecast: Whether to include forecast

        Returns:
            WeatherResponse with current conditions and forecast
        """
        pass


# =============================================================================
# OPENWEATHERMAP PROVIDER
# =============================================================================

class OpenWeatherProvider(WeatherProvider):
    """Weather provider using OpenWeatherMap API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        current_endpoint: Optional[str] = None,
        forecast_endpoint: Optional[str] = None,
        timeout: float = 15.0
    ):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY") or os.getenv("WEATHER_API_KEY")
        self.current_endpoint = (
            current_endpoint or
            os.getenv("OPENWEATHER_CURRENT_ENDPOINT") or
            "https://api.openweathermap.org/data/2.5/weather"
        )
        self.forecast_endpoint = (
            forecast_endpoint or
            os.getenv("OPENWEATHER_FORECAST_ENDPOINT") or
            "https://api.openweathermap.org/data/2.5/forecast"
        )
        self.timeout = timeout
        self._session = requests.Session()

        if not self.api_key:
            logger.warning("OpenWeatherProvider: No API key provided")

    @property
    def name(self) -> str:
        return "openweathermap"

    def get_weather(
        self,
        location: str,
        units: str = "imperial",
        include_forecast: bool = True
    ) -> WeatherResponse:
        """Get weather via OpenWeatherMap API"""
        if not self.api_key:
            raise ToolConfigurationError("OpenWeatherMap API key not configured")

        # Get current weather
        current_data = self._fetch_current(location, units)

        # Get forecast if requested
        forecast = []
        if include_forecast:
            try:
                forecast = self._fetch_forecast(location, units)
            except Exception as e:
                logger.warning(f"Failed to fetch forecast: {e}")

        return self._build_response(current_data, forecast, units)

    def _fetch_current(self, location: str, units: str) -> dict[str, Any]:
        """Fetch current weather"""
        params = {
            "q": location,
            "appid": self.api_key,
            "units": units
        }

        try:
            response = self._session.get(
                self.current_endpoint,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ToolExecutionError(f"Location not found: {location}")
            elif e.response.status_code == 401:
                raise ToolConfigurationError("Invalid OpenWeatherMap API key")
            raise ToolExecutionError(f"OpenWeatherMap API error: {e}")
        except requests.exceptions.RequestException as e:
            raise ToolExecutionError(f"Network error: {e}")

    def _fetch_forecast(self, location: str, units: str) -> list[ForecastPeriod]:
        """Fetch weather forecast"""
        params = {
            "q": location,
            "appid": self.api_key,
            "units": units,
            "cnt": 8  # 24 hours (3-hour intervals)
        }

        response = self._session.get(
            self.forecast_endpoint,
            params=params,
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()

        forecast = []
        for item in data.get("list", [])[:3]:
            time_str = item.get("dt_txt", "").split(" ")[1][:5] if "dt_txt" in item else ""
            forecast.append(ForecastPeriod(
                time=time_str,
                temperature=item["main"]["temp"],
                condition=item["weather"][0]["description"].capitalize()
            ))

        return forecast

    def _build_response(
        self,
        data: dict[str, Any],
        forecast: list[ForecastPeriod],
        units: str
    ) -> WeatherResponse:
        """Build WeatherResponse from API data"""
        main = data["main"]
        weather = data["weather"][0]
        wind = data["wind"]

        condition = WeatherCondition(
            description=weather["description"],
            temperature=main["temp"],
            feels_like=main["feels_like"],
            humidity=main["humidity"],
            wind_speed=wind["speed"],
            clouds=data.get("clouds", {}).get("all"),
            rain_1h=data.get("rain", {}).get("1h"),
            snow_1h=data.get("snow", {}).get("1h")
        )

        return WeatherResponse(
            location=data["name"],
            country=data["sys"]["country"],
            current=condition,
            forecast=forecast,
            units=units
        )


# =============================================================================
# WEATHERAPI PROVIDER (weatherapi.com)
# =============================================================================

class WeatherAPIProvider(WeatherProvider):
    """Weather provider using WeatherAPI.com"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 15.0
    ):
        self.api_key = api_key or os.getenv("WEATHERAPI_KEY")
        self.endpoint = endpoint or os.getenv("WEATHERAPI_ENDPOINT") or "https://api.weatherapi.com/v1/forecast.json"
        self.timeout = timeout
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "weatherapi"

    def get_weather(
        self,
        location: str,
        units: str = "imperial",
        include_forecast: bool = True
    ) -> WeatherResponse:
        """Get weather via WeatherAPI.com"""
        if not self.api_key:
            raise ToolConfigurationError("WeatherAPI.com API key not configured")

        params = {
            "key": self.api_key,
            "q": location,
            "days": 1 if include_forecast else 0,
            "aqi": "no"
        }

        try:
            response = self._session.get(
                self.endpoint,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_response(data, units)

        except requests.exceptions.RequestException as e:
            raise ToolExecutionError(f"WeatherAPI error: {e}")

    def _parse_response(self, data: dict[str, Any], units: str) -> WeatherResponse:
        """Parse WeatherAPI.com response"""
        current = data["current"]
        location_data = data["location"]

        # Convert to requested units
        if units == "imperial":
            temp = current["temp_f"]
            feels = current["feelslike_f"]
            wind = current["wind_mph"]
        else:
            temp = current["temp_c"]
            feels = current["feelslike_c"]
            wind = current["wind_kph"]

        condition = WeatherCondition(
            description=current["condition"]["text"],
            temperature=temp,
            feels_like=feels,
            humidity=current["humidity"],
            wind_speed=wind,
            clouds=current.get("cloud")
        )

        forecast = []
        if "forecast" in data:
            for hour in data["forecast"]["forecastday"][0].get("hour", [])[:3]:
                forecast.append(ForecastPeriod(
                    time=hour["time"].split(" ")[1],
                    temperature=hour["temp_f"] if units == "imperial" else hour["temp_c"],
                    condition=hour["condition"]["text"]
                ))

        return WeatherResponse(
            location=location_data["name"],
            country=location_data["country"],
            current=condition,
            forecast=forecast,
            units=units
        )


# =============================================================================
# PROVIDER FACTORY
# =============================================================================

def get_weather_provider(
    provider: Optional[Union[str, WeatherProvider]] = None,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None
) -> WeatherProvider:
    """
    Get a weather provider by name or return the provided instance.

    Args:
        provider: Provider name ("openweathermap", "weatherapi") or instance
        api_key: API key for the provider
        endpoint: Custom endpoint URL

    Returns:
        WeatherProvider instance
    """
    if isinstance(provider, WeatherProvider):
        return provider

    provider_name = provider or os.getenv("WEATHER_PROVIDER", "openweathermap")

    providers = {
        "openweathermap": OpenWeatherProvider,
        "openweather": OpenWeatherProvider,
        "weatherapi": WeatherAPIProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ToolConfigurationError(f"Unknown weather provider: {provider_name}")

    kwargs = {"api_key": api_key}
    if endpoint:
        if provider_name in ["openweathermap", "openweather"]:
            kwargs["current_endpoint"] = endpoint
        else:
            kwargs["endpoint"] = endpoint

    return provider_class(**kwargs)


# =============================================================================
# WEATHER TOOL
# =============================================================================

class WeatherTool(BaseTool):
    """
    Weather information tool with pluggable providers.

    No hardcoded API endpoints - all configuration via:
    - Constructor parameters
    - Environment variables (WEATHER_PROVIDER, WEATHER_API_KEY, etc.)
    - Custom provider instances

    Usage:
        # Auto-configure from environment
        weather = WeatherTool()

        # Explicit configuration
        weather = WeatherTool(
            provider="openweathermap",
            api_key="your-key",
            units="metric"
        )
    """

    def __init__(
        self,
        provider: Optional[Union[str, WeatherProvider]] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        units: str = "imperial",
        timeout: float = 15.0
    ):
        self._provider = get_weather_provider(provider, api_key, endpoint)
        self._units = units

        # Define schema
        parameters = [
            ParameterSchema(
                name="location",
                type=ParameterType.STRING,
                description="City name (e.g., 'London' or 'London, UK')",
                required=True,
                min_length=1
            ),
            ParameterSchema(
                name="units",
                type=ParameterType.STRING,
                description="Temperature units: 'imperial' (°F) or 'metric' (°C)",
                required=False,
                enum=["imperial", "metric"],
                default="imperial"
            )
        ]

        super().__init__(
            name="get_weather",
            description="Get current weather and forecast for a location",
            parameters=parameters,
            timeout=timeout
        )

        # Add examples
        self.add_example({"name": "get_weather", "args": {"location": "New York"}})
        self.add_example({"name": "get_weather", "args": {"location": "London, UK", "units": "metric"}})

    @property
    def provider(self) -> WeatherProvider:
        """Get the weather provider"""
        return self._provider

    def _execute(self, args: dict[str, Any]) -> Any:
        """Execute the weather lookup"""
        location = args.get("location") or args.get("city") or args.get("place")
        if not location:
            return ToolResult.fail("No location provided")

        units = args.get("units", self._units)

        # Handle multiple locations
        locations = self._parse_locations(str(location))

        if len(locations) > 1:
            results = []
            for loc in locations:
                try:
                    response = self._provider.get_weather(loc, units=units)
                    results.append(response.to_text())
                except Exception as e:
                    results.append(f"Error getting weather for {loc}: {e}")
            return "\n\n".join(results)

        logger.info(f"Getting weather with {self._provider.name}: {locations[0]}")

        response = self._provider.get_weather(locations[0], units=units)
        return response.to_text()

    def _parse_locations(self, location_str: str) -> list[str]:
        """Parse multiple locations from input"""
        location_str = str(location_str)

        if " and " in location_str.lower():
            return [loc.strip() for loc in location_str.lower().split(" and ")]

        if "," in location_str:
            parts = location_str.split(",")
            # "City, Country" format - keep as single location
            if len(parts) == 2:
                return [location_str.strip()]
            # Multiple locations
            return [loc.strip() for loc in parts]

        return [location_str.strip()]
