"""
temperature_logger.py

This module provides functionality for logging temperature data as part of the weather_tracker project.
"""

import os
import datetime

TEMPERATURE_LOG_FILE = 'temperature_log.csv'

def log_temperature(temperature, location):
    """
    Log the current temperature to a CSV file.

    Args:
        temperature (float): The current temperature value.
        location (str): The location where the temperature was measured.

    Returns:
        None
    """
    log_file_path = os.path.join('/app/projects/weather_tracker', TEMPERATURE_LOG_FILE)

    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with open(log_file_path, 'a') as log_file:
        log_file.write(f"{current_time},{location},{temperature}\n")

    print(f"Logged temperature: {temperature}°C at {location}")

def get_temperature_history(location=None):
    """
    Retrieve the temperature history from the log file.

    Args:
        location (str, optional): The location to filter the temperature history by. If not provided, all locations will be returned.

    Returns:
        list: A list of tuples containing the timestamp, location, and temperature.
    """
    log_file_path = os.path.join('/app/projects/weather_tracker', TEMPERATURE_LOG_FILE)

    temperature_history = []

    try:
        with open(log_file_path, 'r') as log_file:
            for line in log_file:
                timestamp, log_location, temperature = line.strip().split(',')
                if location is None or log_location == location:
                    temperature_history.append((timestamp, log_location, float(temperature)))
    except FileNotFoundError:
        print(f"Temperature log file '{TEMPERATURE_LOG_FILE}' not found.")

    return temperature_history