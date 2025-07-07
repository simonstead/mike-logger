import os
import requests
import json
from datetime import datetime

# Project: Weather Tracker
# Purpose: Monitor and track weather data for a specific location

# Working Directory: /app/projects/weather_tracker
# Project Context: weather_tracker

# Configuration
WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
LOCATION = 'New York, NY'
UNITS = 'metric'

def get_current_weather():
    """
    Fetch current weather data for the specified location.
    
    Returns:
        dict: Current weather data, including temperature, humidity, wind speed, and more.
    """
    url = f'http://api.openweathermap.org/data/2.5/weather?q={LOCATION}&appid={WEATHER_API_KEY}&units={UNITS}'
    response = requests.get(url)
    return response.json()

def get_forecast():
    """
    Fetch weather forecast data for the specified location.
    
    Returns:
        dict: Weather forecast data for the next 5 days.
    """
    url = f'http://api.openweathermap.org/data/2.5/forecast?q={LOCATION}&appid={WEATHER_API_KEY}&units={UNITS}'
    response = requests.get(url)
    return response.json()

def main():
    """
    Main function to run the weather tracking application.
    """
    print(f'Weather Tracker - Monitoring weather for {LOCATION}')

    current_weather = get_current_weather()
    print(f'Current Weather: {current_weather["weather"][0]["description"]}')
    print(f'Temperature: {current_weather["main"]["temp"]}°C')
    print(f'Humidity: {current_weather["main"]["humidity"]}%')
    print(f'Wind Speed: {current_weather["wind"]["speed"]} m/s')

    forecast = get_forecast()
    print('\nUpcoming Forecast:')
    for forecast_data in forecast['list']:
        forecast_time = datetime.strptime(forecast_data['dt_txt'], '%Y-%m-%d %H:%M:%S')
        print(f'{forecast_time.strftime("%Y-%m-%d %H:%M")}: {forecast_data["weather"][0]["description"]} - {forecast_data["main"]["temp"]}°C')

if __name__ == '__main__':
    main()