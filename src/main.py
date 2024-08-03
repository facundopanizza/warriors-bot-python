from collections import deque
import cv2 as cv
import pytesseract
import time
import sys
from ppadb.client import Client as AdbClient
from utils.get_image_path import get_image_path
from datetime import datetime, timedelta
import threading
from PIL import Image

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
        self.gold_won_on_battle = 0
        self.gold_held = 0
        self.gold_cost_of_next_upgrade = 0

        self.unit_to_create = unit_to_create

        self.first_troop = {'x': 540, 'y': 2024}
        self.second_troop = {'x': 680, 'y': 2024}
        self.third_troop = {'x': 800, 'y': 2024}

        self.upgrade_menu = {'x': 330, 'y': 2178}
        self.upgrade_production = {'x': 852, 'y': 1307}
        self.battle_menu = {'x': 543, 'y': 2178}
        self.second_skill_coords = {'x': 950, 'y': 1750}
        self.first_skill_coords = {'x': 750, 'y': 1750}
        self.evolution_tab_button = {'x': 663, 'y': 1900}
        self.upgrade_tab_button = {'x': 400, 'y': 1900}
        self.evolve_button = {'x': 550, 'y': 1425}
        self.enter_event_button = {'x': 500, 'y': 1500}

        self.gold_region = (80, 7, 300, 70)
        self.cost_of_production_region = (800, 1245, 980, 1330)
        self.gold_won_on_battle_region = (360, 1024, 800, 1125)


        self.time_of_start_of_battle = None
        self.start_to_create_units = False

        self.start_time = datetime.now()

    def initialize(self):
        devices = self.client.devices()
        if len(devices) == 0:
            print("No devices connected")
            return False

        self.device = devices[0]
        self.setup_pause_handler()
        self.is_in_battle = self.check_if_is_in_battle()
        threading.Thread(target=self.screenshot_loop, daemon=True).start()

        print("Bot started")

        return True

    def setup_pause_handler(self):
        def key_handler():
            while True:
                key = sys.stdin.read(1)
                if key == 'p':
                    self.pause = not self.pause
                    print("Paused" if self.pause else "Resumed")
                elif key == 'u':
                    self.should_upgrade_production = not self.should_upgrade_production
                    print("Upgrading production" if self.should_upgrade_production else "Not upgrading production")
                elif key == 'q':
                    sys.exit(0)
                elif key in ['1', '2', '3']:
                    self.unit_to_create = int(key)
                elif key == 's':
                    print('Gold won so far:', self.gold_won_on_battle)

        threading.Thread(target=key_handler, daemon=True).start()

    def screenshot_loop(self):
        while self.running:
            self.take_screenshot()
            time.sleep(0.02)

    def take_screenshot(self):
        if not self.device:
            print("No device connected")
            return

        image = self.device.screencap()
        try:
            with open('./screencap.png', 'wb') as f:
                f.write(image)
            
            # Convert the image to grayscale and add it to the history
            gray_image = cv.imread('./screencap.png', cv.IMREAD_GRAYSCALE)
            self.screenshot_history.append(gray_image)
            
        except IOError as e:
            print(f"Error writing screenshot: {e}")

    def analyze_image(self, image_name):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            mat = cv.imread('./screencap.png', cv.IMREAD_GRAYSCALE)
            template = cv.imread(get_image_path(image_name), cv.IMREAD_GRAYSCALE)
            result = cv.matchTemplate(mat, template, cv.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv.minMaxLoc(result)

            # print(f"[{current_time}] Analyzing image {image_name} - {max_val}")

            match_threshold = 0.7
            if max_val < match_threshold:
                return None

            center_x = max_loc[0] + template.shape[1] // 2
            center_y = max_loc[1] + template.shape[0] // 2

            return {'x': center_x, 'y': center_y}
        except Exception as e:
            print(f"[{current_time}] Error analyzing image: {e}")
            return None

    def touch_screen(self, x, y):
        if not self.device:
            print("No device connected")
            return

        self.device.shell(f"input tap {x} {y}")

    def create_unit(self):
        if self.unit_to_create == 1:
            # print("Creating unit 1")
            self.touch_screen(self.first_troop['x'], self.first_troop['y'])
        elif self.unit_to_create == 2:
            # print("Creating unit 2")
            self.touch_screen(self.second_troop['x'], self.second_troop['y'])
        elif self.unit_to_create == 3:
            # print("Creating unit 3")
            self.touch_screen(self.third_troop['x'], self.third_troop['y'])
        else:
            print(f"Invalid troop number: {self.unit_to_create}. Creating default unit 2")
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

        if self.time_of_start_of_battle and (datetime.now() - self.time_of_start_of_battle).total_seconds() > 9:
            self.touch_screen(self.first_skill_coords['x'], self.first_skill_coords['y'])
            self.touch_screen(self.second_skill_coords['x'], self.second_skill_coords['y'])
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
            self.gold_won_on_battle += self.read_number_from_screen(self.gold_won_on_battle_region)

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
        self.gold_held = self.read_number_from_screen(self.gold_region)

        # if self.should_upgrade_production and self.gold_held >= self.gold_cost_of_next_upgrade:
        if self.should_upgrade_production:
            self.touch_screen(self.upgrade_menu['x'], self.upgrade_menu['y'])

            time.sleep(0.3)

            self.touch_screen(self.evolution_tab_button['x'], self.evolution_tab_button['y'])

            time.sleep(0.1)

            self.touch_screen(self.evolve_button['x'], self.evolve_button['y'])

            time.sleep(0.3)

            self.touch_screen(500, 1900)

            time.sleep(0.1)

            self.touch_screen(self.upgrade_tab_button['x'], self.upgrade_tab_button['y'])

            time.sleep(0.1)

            self.device.shell(f"input touchscreen swipe {self.upgrade_production['x']} {self.upgrade_production['y']} {self.upgrade_production['x']} {self.upgrade_production['y']} 2000")

            self.gold_cost_of_next_upgrade = self.read_number_from_screen(self.cost_of_production_region)

            time.sleep(0.3)

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
            print("Could not find battle button")
            return

        start_time = time.time()
        while not self.is_in_battle and time.time() - start_time < 10:
            self.touch_screen(buttonToUse['x'], buttonToUse['y'])
            time.sleep(1)
            self.is_in_battle = self.check_if_is_in_battle()
            
        self.time_of_start_of_battle = datetime.now()
        self.start_to_create_units = False

    def read_number_from_screen(self, region=None):
        try:
            image = Image.open('./screencap.png')

            if region:
                image = image.crop(region)

            text = pytesseract.image_to_string(image)

            clean_digits = ''.join(filter(lambda x: x.isdigit() or x == '.', text))

            amount = float(clean_digits)

            # Check for suffixes in the text
            lower_text = text.lower()
            if 'm' in lower_text:
                amount *= 1000000
            elif 'k' in lower_text:
                amount *= 1000

            return amount
        except Exception as e:
            print(f"Error in read_number_from_screen: {e}")
            return 0

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
            print(f"Detected stuck state ({similar_count + 1} similar screenshots). Restarting bot.")
            self.restart_bot()
            return True

        return False

    def restart_bot(self):
        print("Restarting the bot...")
        self.running = False

        self.restart_adb_application()

        new_bot = GameAutomation(self.unit_to_create, self.should_upgrade_production)
        if new_bot.initialize():
            new_bot.run()

    def restart_adb_application(self):
        if not self.device:
            print("No device connected")
            return

        package_name = "com.vjsjlqvlmp.wearewarriors"  # Replace with the actual package name of your game

        print(f"Stopping {package_name}...")
        self.device.shell(f"am force-stop {package_name}")
        time.sleep(2)  # Wait for the app to fully stop

        print(f"Starting {package_name}...")
        self.device.shell(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        time.sleep(10)  # Wait for the app to fully start

        self.touch_screen(self.enter_event_button['x'], self.enter_event_button['y'])

        print("Application restarted.")

    def run(self):
        while self.running:
            if self.pause:
                continue

            if self.check_if_stuck():
                break

            # Check if an hour has passed
            if datetime.now() - self.start_time > timedelta(hours=1):
                print("An hour has passed. Restarting the bot...")
                self.restart_bot()
                break

            self.gold_held = self.read_number_from_screen(self.gold_region)

            self.loop_count += 1
            self.is_in_battle = self.check_if_is_in_battle()

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

        print("Bot instance stopped.")

if __name__ == "__main__":
    try:
        game_automation = GameAutomation()
        if game_automation.initialize():
            game_automation.run()
    except Exception as e:
        print(e)