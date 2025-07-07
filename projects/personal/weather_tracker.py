import os
import requests
from datetime import datetime

# Weather Tracker Project

# This project is designed to monitor weather data and provide insights into the local weather conditions.

# Working Directory: /app/projects/personal
# Project Context: personal

# 1. Create the necessary directories and files
project_dir = '/app/projects/personal/weather_tracker'
if not os.path.exists(project_dir):
    os.makedirs(project_dir)

# 2. Fetch weather data from an API
api_key = 'your_api_key_here'
city = 'New York'
api_url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric'

response = requests.get(api_url)
weather_data = response.json()

# 3. Process and store the weather data
current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
temperature = weather_data['main']['temp']
description = weather_data['weather'][0]['description']

weather_report = f'''
Weather Report
Date and Time: {current_time}
Location: {city}
Temperature: {temperature}°C
Description: {description}
'''

report_file = os.path.join(project_dir, 'weather_report.txt')
with open(report_file, 'w') as f:
    f.write(weather_report)

print(f'Weather report saved to {report_file}')