from collections import deque
import cv2 as cv
import pytesseract
import time
import sys
from ppadb.client import Client as AdbClient
from utils.get_image_path import get_image_path
from datetime import datetime, timedelta
import threading
from PIL import Image, ImageEnhance
import numpy as np
import curses
import re
import cv2
import logging
import msvcrt

class GameAutomation:
    def __init__(self, unit_to_create=2, should_upgrade_production=True):
        self.client = AdbClient(host="127.0.0.1", port=5037)
        self.device = None
        self.loop_count = 0
        self.is_in_battle = False
        self.pause = False
        self.should_upgrade_production = should_upgrade_production
        self.screenshot_lock = threading.Lock()
        self.screenshot_history = deque(maxlen=60)
        self.stuck_threshold = 0.95
        self.min_stuck_screenshots = 50
        self.running = True
        self.gold_won_on_last_battle = 0
        self.gold_held = 0
        self.gold_cost_of_next_upgrade = 0
        self.evolve_amount = 0
        self.key_handler_thread = None
        self.screenshot_thread = None
        self.debug = False
        self.setup_logging()
        self.is_saving_to_evolve = False

        self.unit_to_create = unit_to_create

        self.first_troop = {'x': 540, 'y': 2024}
        self.second_troop = {'x': 680, 'y': 2024}
        self.third_troop = {'x': 800, 'y': 2024}

        self.upgrade_menu = {'x': 330, 'y': 2178}
        self.upgrade_production = {'x': 852, 'y': 1307}
        self.battle_menu = {'x': 543, 'y': 2178}

        self.third_skill_coords = {'x': 570, 'y': 1750}
        self.second_skill_coords = {'x': 950, 'y': 1750}
        self.first_skill_coords = {'x': 750, 'y': 1750}

        self.hero_coords = {'x': 130, 'y': 1750}

        self.evolution_tab_button = {'x': 663, 'y': 1900}
        self.upgrade_tab_button = {'x': 400, 'y': 1900}
        self.evolve_button = {'x': 550, 'y': 1425}
        self.enter_event_button = {'x': 500, 'y': 1500}

        self.gold_region = (80, 7, 300, 70)
        self.cost_of_production_region = (800, 1245, 980, 1300)
        self.gold_won_on_battle_region = (360, 1000, 800, 1125)
        self.evolve_amount_region = (370, 1450, 700, 1530)

        self.time_of_start_of_battle = None
        self.start_to_create_units = False

        self.start_time = datetime.now()

        self.menu_items = [
            ("Upgrade Production: ON", self.toggle_upgrade_production),
            ("Debug Mode: OFF", self.toggle_debug),
            ("Pause/Resume: Running", self.toggle_pause),
            ("Debug Number Reading", self.debug_number_reading),
            ("Quit", self.quit_program)
        ]
        self.selected_menu_item = 0
        self.screen = None

    def initialize(self):
        devices = self.client.devices()
        if len(devices) == 0:
            self.debug_print("No devices connected")
            return False

        self.device = devices[0]
        self.setup_pause_handler()
        self.is_in_battle = self.check_if_is_in_battle()
        self.screenshot_thread = threading.Thread(target=self.screenshot_loop, daemon=True)
        self.screenshot_thread.start()

        self.screen = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self.screen.keypad(True)
        curses.curs_set(0)
        self.setup_ui_handler()

        self.debug_print("Bot started")

        return True

    def setup_pause_handler(self):
        def key_handler():
            while self.running:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b'p':
                        self.pause = not self.pause
                        print("Paused" if self.pause else "Resumed")
                    elif key == b'u':
                        self.should_upgrade_production = not self.should_upgrade_production
                        print("Upgrading production" if self.should_upgrade_production else "Not upgrading production")
                    elif key == b'q':
                        self.running = False
                        print("Quitting...")
                        sys.exit(0)
                    elif key in [b'1', b'2', b'3']:
                        self.unit_to_create = int(key.decode())
                        print(f"Unit to create set to {self.unit_to_create}")
                    elif key == b's':
                        print('Gold won on last battle:', self.gold_won_on_last_battle)
                    elif key == b'd':
                        self.debug = not self.debug
                        print(f"Debug mode {'enabled' if self.debug else 'disabled'}")
                    elif key == b'n':
                        self.debug_number_reading()
                time.sleep(0.1)

        self.key_handler_thread = threading.Thread(target=key_handler, daemon=True)
        self.key_handler_thread.start()

    def setup_ui_handler(self):
        def ui_handler():
            while self.running:
                key = self.screen.getch()
                if key != curses.ERR:  # If a key was pressed
                    self.handle_key_press(key)
                    self.draw_ui()  # Redraw UI immediately after key press
                time.sleep(0.1)

        self.ui_thread = threading.Thread(target=ui_handler, daemon=True)
        self.ui_thread.start()

        def redraw_ui():
            while self.running:
                self.draw_ui()
                time.sleep(1)  # Redraw every second

        self.redraw_thread = threading.Thread(target=redraw_ui, daemon=True)
        self.redraw_thread.start()

    def draw_ui(self):
        self.screen.clear()
        height, width = self.screen.getmaxyx()

        # Title
        title = "Game Automation Control Panel"
        self.screen.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)

        # Menu items
        for idx, (item_name, _) in enumerate(self.menu_items):
            y = idx + 2
            x = 2
            if idx == self.selected_menu_item:
                self.screen.addstr(y, x, f"> {item_name}", curses.A_REVERSE)
            else:
                self.screen.addstr(y, x, f"  {item_name}")

        # Unit selection
        unit_y = len(self.menu_items) + 3
        self.screen.addstr(unit_y, 2, "Unit to create:")
        for i in range(1, 4):
            if i == self.unit_to_create:
                self.screen.addstr(unit_y, 20 + (i-1)*4, f"[{i}]", curses.A_REVERSE)
            else:
                self.screen.addstr(unit_y, 20 + (i-1)*4, f" {i} ")

        # Status information
        status_y = unit_y + 2
        self.screen.addstr(status_y, 2, f"Gold held: {self.format_number(self.gold_held)}")
        self.screen.addstr(status_y + 1, 2, f"Gold won on last battle: {self.format_number(self.gold_won_on_last_battle)}")
        self.screen.addstr(status_y + 2, 2, f"Upgrade production cost: {self.format_number(self.gold_cost_of_next_upgrade)}")
        self.screen.addstr(status_y + 3, 2, f"In battle: {'Yes' if self.is_in_battle else 'No'}")
        self.screen.addstr(status_y + 4, 2, f"Evolve amount: {self.format_number(self.evolve_amount)}")
        self.screen.addstr(status_y + 5, 2, f"Bot running time: {str(datetime.now() - self.start_time).split('.')[0]}")
        self.screen.addstr(status_y + 6, 2, f"Is saving to evolve: {'Yes' if self.is_saving_to_evolve else 'No'}")

        # Hotkey information
        hotkey_y = status_y + 9
        self.screen.addstr(hotkey_y, 2, "Hotkeys: (P)ause, (D)ebug, (U)pgrade, (Q)uit, (N)umber reading debug")

        self.screen.refresh()

    def handle_key_press(self, key):
        if key == curses.KEY_UP:
            self.selected_menu_item = (self.selected_menu_item - 1) % len(self.menu_items)
        elif key == curses.KEY_DOWN:
            self.selected_menu_item = (self.selected_menu_item + 1) % len(self.menu_items)
        elif key == ord('\n') or key == ord(' '):  # Enter or Space
            _, action = self.menu_items[self.selected_menu_item]
            action()
        elif key in [ord('1'), ord('2'), ord('3')]:
            self.unit_to_create = int(chr(key))
        elif key in [ord('p'), ord('P')]:
            self.toggle_pause()
        elif key in [ord('d'), ord('D')]:
            self.toggle_debug()
        elif key in [ord('u'), ord('U')]:
            self.toggle_upgrade_production()
        elif key in [ord('q'), ord('Q')]:
            self.quit_program()
        elif key in [ord('n'), ord('N')]:  # 'N' for Number reading debug
            self.debug_number_reading()

    def toggle_upgrade_production(self):
        self.should_upgrade_production = not self.should_upgrade_production
        self.menu_items[0] = (f"Upgrade Production: {'ON' if self.should_upgrade_production else 'OFF'}", self.toggle_upgrade_production)

    def toggle_debug(self):
        self.debug = not self.debug
        self.menu_items[1] = (f"Debug Mode: {'ON' if self.debug else 'OFF'}", self.toggle_debug)
        self.debug_print(f"Debug mode {'enabled' if self.debug else 'disabled'}")

    def toggle_pause(self):
        self.pause = not self.pause
        self.menu_items[2] = (f"Pause/Resume: {'Paused' if self.pause else 'Running'}", self.toggle_pause)

    def quit_program(self):
        self.running = False
        curses.endwin()
        sys.exit(0)

    def screenshot_loop(self):
        while True:
            self.take_screenshot()
            time.sleep(0.02)

    def take_screenshot(self):
        if not self.device:
            self.debug_print("No device connected")
            return

        image = self.device.screencap()
        try:
            with open('./screencap.png', 'wb') as f:
                f.write(image)
            
            # Convert the image to grayscale and add it to the history
            gray_image = cv.imread('./screencap.png', cv.IMREAD_GRAYSCALE)
            self.screenshot_history.append(gray_image)
            
        except IOError as e:
            self.debug_print(f"Error writing screenshot: {e}")

    def analyze_image(self, image_name):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            mat = cv.imread('./screencap.png', cv.IMREAD_GRAYSCALE)
            template = cv.imread(get_image_path(image_name), cv.IMREAD_GRAYSCALE)
            result = cv.matchTemplate(mat, template, cv.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv.minMaxLoc(result)

            self.debug_print(f"[{current_time}] Analyzing image {image_name} - {max_val}")

            match_threshold = 0.7
            if max_val < match_threshold:
                return None

            center_x = max_loc[0] + template.shape[1] // 2
            center_y = max_loc[1] + template.shape[0] // 2

            return {'x': center_x, 'y': center_y}
        except Exception as e:
            self.debug_print(f"[{current_time}] Error analyzing image: {e}")
            return None

    def touch_screen(self, x, y):
        if not self.device:
            self.debug_print("No device connected")
            return

        self.device.shell(f"input tap {x} {y}")

    def create_unit(self):
        if self.unit_to_create == 1:
            self.debug_print("Creating unit 1")
            self.touch_screen(self.first_troop['x'], self.first_troop['y'])
        elif self.unit_to_create == 2:
            self.debug_print("Creating unit 2")
            self.touch_screen(self.second_troop['x'], self.second_troop['y'])
        elif self.unit_to_create == 3:
            self.debug_print("Creating unit 3")
            self.touch_screen(self.third_troop['x'], self.third_troop['y'])
        else:
            self.debug_print(f"Invalid troop number: {self.unit_to_create}. Creating default unit 2")
            self.touch_screen(self.second_troop['x'], self.second_troop['y'])
            

    def check_if_is_in_battle(self):
        is_in_battle = self.analyze_image('is-in-battle.png')
        return bool(is_in_battle)

    def check_if_is_on_menu(self):
        is_on_menu = self.analyze_image('market-menu-button.png')
        return bool(is_on_menu)

    def handle_battle_state(self):
        if self.start_to_create_units:
            self.create_unit()

        if self.time_of_start_of_battle and (datetime.now() - self.time_of_start_of_battle).total_seconds() > 7.5:
            self.touch_screen(self.first_skill_coords['x'], self.first_skill_coords['y'])
            self.touch_screen(self.second_skill_coords['x'], self.second_skill_coords['y'])
            self.touch_screen(self.third_skill_coords['x'], self.third_skill_coords['y'])
            self.touch_screen(self.hero_coords['x'], self.hero_coords['y'])

            self.time_of_start_of_battle = None
            self.start_to_create_units = True

        close_battle_button = self.analyze_image('close-battle-button.png')
        self.is_in_battle = self.check_if_is_in_battle()

        if close_battle_button:
            self.exit_battle()
            self.is_in_battle = False

    def exit_battle(self):
        close_battle_button = self.analyze_image('close-battle-button.png')

        if close_battle_button:
            self.gold_won_on_last_battle = self.read_number_from_screen(self.gold_won_on_battle_region, force_new_screenshot=True)

            self.touch_screen(close_battle_button['x'], close_battle_button['y'])
            time.sleep(2)

        stuck_button = self.analyze_image('are-you-stuck-button.png')
        if stuck_button:
            self.touch_screen(stuck_button['x'], stuck_button['y'])

    def handle_menu_state(self):
        stuck_button = self.analyze_image('are-you-stuck-button.png')

        if stuck_button:
            self.touch_screen(stuck_button['x'], stuck_button['y'])

        self.upgrade_and_start_battle()

    def upgrade_and_start_battle(self):
        time.sleep(0.5)
        self.gold_held = self.read_number_from_screen(self.gold_region, force_new_screenshot=True)

        if self.should_upgrade_production and (self.gold_held >= self.gold_cost_of_next_upgrade or self.gold_held == 0 or self.gold_cost_of_next_upgrade == 0 or self.gold_held >= self.evolve_amount):
            self.touch_screen(self.upgrade_menu['x'], self.upgrade_menu['y'])

            time.sleep(0.3)

            self.touch_screen(self.evolution_tab_button['x'], self.evolution_tab_button['y'])

            time.sleep(0.1)

            self.evolve_amount = self.read_number_from_screen(self.evolve_amount_region, force_new_screenshot=True)

            self.touch_screen(self.evolve_button['x'], self.evolve_button['y'])

            time.sleep(0.3)

            self.touch_screen(500, 1900)

            isBuyCoinsModal = self.analyze_image('close_buy_coins.png')

            if isBuyCoinsModal:
                time.sleep(0.3)
                self.touch_screen(isBuyCoinsModal['x'], isBuyCoinsModal['y'])
                isBuyCoinsModal = None

            time.sleep(0.1)

            self.touch_screen(self.upgrade_tab_button['x'], self.upgrade_tab_button['y'])

            time.sleep(0.1)

            self.gold_cost_of_next_upgrade = self.read_number_from_screen(self.cost_of_production_region, force_new_screenshot=True)

            time.sleep(0.1)
            if (self.evolve_amount != 0 and self.gold_won_on_last_battle != 0 and self.evolve_amount / self.gold_won_on_last_battle > 20) or self.gold_cost_of_next_upgrade == 0:
                self.device.shell(f"input touchscreen swipe {self.upgrade_production['x']} {self.upgrade_production['y']} {self.upgrade_production['x']} {self.upgrade_production['y']} 2000")

                isBuyCoinsModal = self.analyze_image('close_buy_coins.png')

                if isBuyCoinsModal:
                    time.sleep(0.3)
                    self.touch_screen(isBuyCoinsModal['x'], isBuyCoinsModal['y'])

                time.sleep(0.3)
                self.is_saving_to_evolve = False
            else:
                self.is_saving_to_evolve = True

            self.gold_cost_of_next_upgrade = self.read_number_from_screen(self.cost_of_production_region, force_new_screenshot=True)
        else:
            self.is_saving_to_evolve = True

        buttonToUse = None

        start_time = time.time()
        while not buttonToUse and time.time() - start_time < 10:
            self.touch_screen(self.battle_menu['x'], self.battle_menu['y'])
            battle_button = self.analyze_image('start-battle-button.png')
            battle_brown_button = self.analyze_image('start-battle-brown-button.png')

            if battle_brown_button:
                buttonToUse = battle_brown_button
            elif battle_button:
                buttonToUse = battle_button

        # Add a check to ensure buttonToUser is not None
        if buttonToUse is None:
            self.debug_print("Could not find battle button")
            return

        start_time = time.time()
        while not self.is_in_battle and time.time() - start_time < 10:
            self.touch_screen(buttonToUse['x'], buttonToUse['y'])
            time.sleep(1)
            self.is_in_battle = self.check_if_is_in_battle()
            
        self.time_of_start_of_battle = datetime.now()
        self.start_to_create_units = False

    def read_number_from_screen(self, region=None, force_new_screenshot=False):
        try:
            if force_new_screenshot:
                self.take_number_screenshot()
                time.sleep(0.1)  # Short delay to ensure the screenshot is saved

            image = Image.open('./number_screencap.png')
            image = image.convert('L')  # Convert to grayscale


            if region:
                image = image.crop(region)
                image.save('cropped_number.png')

            text = pytesseract.image_to_string(image, lang='eng')

            print(f"Raw Text: {text}")
            logging.debug(f"Raw Text: {text}")

            # Remove all non-alphanumeric characters except '.' and spaces
            cleaned_text = re.sub(r'[^0-9a-zA-Z.\s]', '', text)

            # Split the text into words
            words = cleaned_text.split()

            # Find the first word that starts with a digit
            number_word = next((word for word in words if word[0].isdigit()), None)

            if not number_word:
                return 0

            # Extract only digits and decimal point
            clean_digits = ''.join(filter(lambda x: x.isdigit() or x == '.', number_word))

            # Handle cases where the decimal point might be misread
            if clean_digits.count('.') > 1:
                clean_digits = clean_digits.replace('.', '', clean_digits.count('.') - 1)

            amount = float(clean_digits)

            print(f"Raw Text: {text}, Cleaned Text: {clean_digits}, Amount: {amount}")
            logging.debug(f"Raw Text: {text}, Cleaned Text: {clean_digits}, Amount: {amount}")

            # Check for suffixes in the original text
            lower_text = text.lower()
            if 'm' in lower_text:
                amount *= 1000000
            elif 'b' in lower_text:
                amount *= 1000000000
            elif 'k' in lower_text:
                amount *= 1000

            return amount
        except Exception as e:
            self.debug_print(f"Error in read_number_from_screen: {e}")
            return 0

    def take_number_screenshot(self):
        if not self.device:
            self.debug_print("No device connected")
            return

        image = self.device.screencap()
        try:
            with open('./number_screencap.png', 'wb') as f:
                f.write(image)
        except IOError as e:
            self.debug_print(f"Error writing number screenshot: {e}")

    def check_if_stuck(self):
        if len(self.screenshot_history) < self.min_stuck_screenshots:
            return False

        reference = self.screenshot_history[-1]
        similar_count = 0

        for i in range(-2, -self.min_stuck_screenshots - 1, -1):
            similarity = cv.matchTemplate(reference, self.screenshot_history[i], cv.TM_CCOEFF_NORMED)[0][0]
            if similarity > self.stuck_threshold:
                similar_count += 1
            else:
                break

        if similar_count >= self.min_stuck_screenshots - 1:
            self.debug_print(f"Detected stuck state ({similar_count + 1} similar screenshots). Restarting bot.")
            return True

        self.screenshot_history.clear()

        return False

    def debug_print(self, message):
        if self.debug:
            logging.debug(message)

    def format_number(self, number):
        return f"{number:,.2f}"

    def debug_number_reading(self):
        self.pause = True
        selected_option = 0
        options = [
            ("Gold Held", self.gold_region),
            ("Gold Won on Battle", self.gold_won_on_battle_region),
            ("Gold Cost of Next Upgrade", self.cost_of_production_region),
            ("Evolve Amount", self.evolve_amount_region)
        ]

        while True:
            self.screen.clear()
            self.screen.addstr(0, 0, "Debug Number Reading")
            for i, (label, _) in enumerate(options):
                if i == selected_option:
                    self.screen.addstr(i+2, 0, f"> {label}", curses.A_REVERSE)
                else:
                    self.screen.addstr(i+2, 0, f"  {label}")
            self.screen.addstr(len(options)+3, 0, "Use arrow keys to select, Enter to debug, or any other key to return")
            self.screen.refresh()

            key = self.screen.getch()
            if key == curses.KEY_UP:
                selected_option = (selected_option - 1) % len(options)
            elif key == curses.KEY_DOWN:
                selected_option = (selected_option + 1) % len(options)
            elif key == ord('\n'):  # Enter key
                label, region = options[selected_option]
                self.debug_selected_number(label, region)
            else:
                break

    def debug_selected_number(self, label, region):
        self.screen.clear()
        self.take_number_screenshot()
        number = self.read_number_from_screen(region)
        
        image = cv2.imread('./number_screencap.png')
        x, y, w, h = region
        cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imwrite('./debug_number_screenshot.png', image)

        self.screen.addstr(0, 0, f"Debugging {label}")
        self.screen.addstr(2, 0, f"Detected number: {self.format_number(number)}")
        self.screen.addstr(4, 0, "A debug screenshot has been saved as 'debug_number_screenshot.png'")
        self.screen.addstr(5, 0, "Press any key to continue")
        self.screen.refresh()
        self.screen.getch()

    def setup_logging(self):
        logging.basicConfig(filename='debug.log', level=logging.DEBUG, 
                            format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    def run(self):
        while self.running:
            if not self.pause:
                self.loop_count += 1
                self.is_in_battle = self.check_if_is_in_battle()

                self.debug_print(f"Loop {self.loop_count}: In battle: {self.is_in_battle}, Gold: {self.gold_held}")

                if self.is_in_battle:
                    self.handle_battle_state()
                    continue

                is_on_menu = self.check_if_is_on_menu()

                if is_on_menu:
                    self.handle_menu_state()
                else:
                    self.is_in_battle = True
                    self.touch_screen(500, 1900)
                    close_battle_button = self.analyze_image('close-battle-button.png')

                    if close_battle_button:
                        self.exit_battle()

            time.sleep(0.1)

        curses.endwin()
        print("Bot instance stopped.")

if __name__ == "__main__":
    try:
        game_automation = GameAutomation()
        if game_automation.initialize():
            game_automation.run()
    except Exception as e:
        curses.endwin()
        print(e)