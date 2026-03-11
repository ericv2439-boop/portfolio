import cv2
import numpy as np
import time

# Window size
width, height = 800, 600

# Login credentials
USERNAME = "portfolio"
PASSWORD = "access123"

# Static skill values
skills = {
    "Python": 96,
    "HTML": 90,
    "SQL": 86,
    "English": 98
}

# Login variables
user_input = ""
pass_input = ""
active_field = "user"
login_success = False
running = True  # loop control

# Cursor blinking
blink = True
last_blink = time.time()
blink_interval = 0.5

# Button coordinates
login_button_coords = (width//2 - 60, 340, width//2 + 60, 380)  # moved lower from password box
close_button_coords = (width - 120, height - 60, width - 20, height - 20)  # bottom-right

# Draw centered text
def draw_text(img, text, pos, font_scale=1, thickness=2, color=(0,255,0)):
    font = cv2.FONT_HERSHEY_SIMPLEX
    size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    x, y = pos
    cv2.putText(img, text, (x - size[0] // 2, y), font, font_scale, color, thickness)

# Draw login screen
def login_screen():
    global blink, last_blink
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (0, 30, 0)  # dark green background

    draw_text(img, "DIGITAL CURRICULUM LOGIN", (width//2, 100), 1.2, 3)
    draw_text(img, "Note for reviewer:", (width//2, 150), 0.7, 2)
    draw_text(img, "User: portfolio", (width//2, 180), 0.7, 2)
    draw_text(img, "Password: access123", (width//2, 210), 0.7, 2)

    # Input boxes
    box_w, box_h = 300, 30
    user_box = (width//2 - box_w//2, 250, width//2 + box_w//2, 280)
    pass_box = (width//2 - box_w//2, 290, width//2 + box_w//2, 320)
    cv2.rectangle(img, (user_box[0], user_box[1]), (user_box[2], user_box[3]), (0,255,0), 2)
    cv2.rectangle(img, (pass_box[0], pass_box[1]), (pass_box[2], pass_box[3]), (0,255,0), 2)

    # Draw user input
    draw_text(img, user_input, (width//2, 268), 0.8, 2)
    hidden_pass = "*" * len(pass_input)
    draw_text(img, hidden_pass, (width//2, 308), 0.8, 2)

    # Blinking cursor
    current_time = time.time()
    if current_time - last_blink > blink_interval:
        blink = not blink
        last_blink = current_time

    if blink:
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = 2
        scale = 0.8
        if active_field == "user":
            text = user_input
            y_pos = 268
            box = user_box
        else:
            text = hidden_pass
            y_pos = 308
            box = pass_box

        # Cursor starts centered + moves with text
        text_size = cv2.getTextSize(text, font, scale, thickness)[0][0]
        cursor_x = box[0] + (box[2]-box[0])//2 - text_size//2 + text_size
        cursor_y1 = box[1] + 5
        cursor_y2 = box[3] - 5
        cv2.line(img, (cursor_x, cursor_y1), (cursor_x, cursor_y2), (0,255,0), 2)

    # LOGIN button (green)
    x1, y1, x2, y2 = login_button_coords
    cv2.rectangle(img, (x1, y1), (x2, y2), (0,200,0), -1)
    draw_text(img, "LOGIN", ((x1+x2)//2, (y1+y2)//2 + 5), 0.8, 2, (0,0,0))

    # CLOSE button (green)
    cx1, cy1, cx2, cy2 = close_button_coords
    cv2.rectangle(img, (cx1, cy1), (cx2, cy2), (0,200,0), -1)
    draw_text(img, "CLOSE", ((cx1+cx2)//2, (cy1+cy2)//2 + 5), 0.7, 2, (0,0,0))

    return img

# Dashboard screen
def dashboard():
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (0, 20, 0)

    draw_text(img, "CURRICULUM PORTFOLIO", (width//2, 50), 1.2, 3)
    draw_text(img, "Portfolio Candidate - Developer", (width//2, 100), 0.8, 2)

    y_start = 180
    for i, (skill, value) in enumerate(skills.items()):
        y = y_start + i*70
        draw_text(img, f"{skill}: {value}%", (width//2, y), 0.9, 2)
        bar_width = int(value / 100 * 400)
        cv2.rectangle(img, (width//2 - 200, y+10), (width//2 - 200 + bar_width, y+30), (0, 255, 0), -1)
        cv2.rectangle(img, (width//2 - 200, y+10), (width//2 + 200, y+30), (0, 150, 0), 2)

    # CLOSE button on dashboard (green)
    cx1, cy1, cx2, cy2 = close_button_coords
    cv2.rectangle(img, (cx1, cy1), (cx2, cy2), (0,200,0), -1)
    draw_text(img, "CLOSE", ((cx1+cx2)//2, (cy1+cy2)//2 + 5), 0.7, 2, (0,0,0))

    return img

# Mouse click
def mouse_event(event, x, y, flags, param):
    global active_field, login_success, running
    if event == cv2.EVENT_LBUTTONDOWN:
        # LOGIN button
        x1, y1, x2, y2 = login_button_coords
        if x1 <= x <= x2 and y1 <= y <= y2:
            if user_input == USERNAME and pass_input == PASSWORD:
                login_success = True

        # Input boxes
        if 250 <= y <= 280 and width//2 - 150 <= x <= width//2 + 150:
            active_field = "user"
        elif 290 <= y <= 320 and width//2 - 150 <= x <= width//2 + 150:
            active_field = "pass"

        # CLOSE button
        cx1, cy1, cx2, cy2 = close_button_coords
        if cx1 <= x <= cx2 and cy1 <= y <= cy2:
            running = False  # graceful exit

cv2.namedWindow("Portfolio")
cv2.setMouseCallback("Portfolio", mouse_event)

while running:
    if not login_success:
        img = login_screen()
    else:
        img = dashboard()

    cv2.imshow("Portfolio", img)
    key = cv2.waitKey(1) & 0xFF

    # Typing input
    if not login_success:
        if key == 8:  # backspace
            if active_field == "user":
                user_input = user_input[:-1]
            else:
                pass_input = pass_input[:-1]
        elif key == 13:  # enter
            if user_input == USERNAME and pass_input == PASSWORD:
                login_success = True
        elif 32 <= key <= 126:  # printable characters
            if active_field == "user":
                user_input += chr(key)
            else:
                pass_input += chr(key)

    # Quit on 'q'
    if key == ord('q'):
        running = False

cv2.destroyAllWindows()
