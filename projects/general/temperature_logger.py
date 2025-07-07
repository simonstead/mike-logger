"""
temperature_logger.py

This module provides temperature logging functionality for the weather_tracker project.
It includes the following features:

- Periodic temperature data collection from a sensor
- Logging of temperature data to a file
- Configurable logging interval and file path
"""

import time
import os
import logging

# Configure logging
logging.basicConfig(
    filename='temperature_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Temperature sensor configuration
SENSOR_PIN = 4
LOGGING_INTERVAL = 60  # seconds

def read_temperature():
    """
    Read the current temperature from the sensor.
    
    Returns:
        float: The current temperature in degrees Celsius.
    """
    # Implement temperature sensor reading logic here
    return 25.3

def log_temperature():
    """
    Log the current temperature to the temperature log file.
    """
    temperature = read_temperature()
    logging.info(f"Current temperature: {temperature:.2f}°C")

def main():
    """
    Main function to run the temperature logging process.
    """
    while True:
        log_temperature()
        time.sleep(LOGGING_INTERVAL)

if __name__ == "__main__":
    main()