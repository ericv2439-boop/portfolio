import pyautogui
import time

# Frequency in seconds
INTERVAL = 5

print("Script started. Press Ctrl+C in this window to stop.")
print(f"Pressing 'right arrow' every {INTERVAL} seconds...")

try:
    while True:
        # Perform the key press
        pyautogui.press('right')
        
        # Wait for the specified interval
        time.sleep(INTERVAL)
        
except KeyboardInterrupt:
    print("\nScript stopped by user.")
