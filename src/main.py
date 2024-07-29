import cv2 as cv
import os
# import pytesseract
import time
import sys
from ppadb.client import Client as AdbClient
from utils.wait import wait
from utils.get_image_path import get_image_path
from datetime import datetime
import threading
import msvcrt
# from PIL import Image

class GameAutomation:
    def __init__(self):
        self.client = AdbClient(host="127.0.0.1", port=5037)
        self.device = None
        self.loop_count = 0
        self.is_in_battle = False
        self.pause = False
        self.should_upgrade_production = True
        self.screenshot_lock = threading.Lock()

        self.first_troop = {'x': 680, 'y': 2024}
        self.upgrade_menu = {'x': 330, 'y': 2178}
        self.upgrade_production = {'x': 852, 'y': 1307}
        self.battle_menu = {'x': 543, 'y': 2178}

    def initialize(self):
        devices = self.client.devices()
        if len(devices) == 0:
            print("No devices connected")
            return False

        self.device = devices[0]
        self.setup_pause_handler()
        self.is_in_battle = self.check_if_is_in_battle()
        threading.Thread(target=self.screenshot, daemon=True).start()

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

        threading.Thread(target=key_handler, daemon=True).start()

    def screenshot(self):
        while True:
            if not self.device:
                print("No device connected")
                return

            image = self.device.screencap()
            try:
                with open('./screencap.png', 'wb') as f:
                    f.write(image)
            except IOError as e:
                print(f"Error writing screenshot: {e}")
                continue

            time.sleep(0.02)

    def analyze_image(self, image_name):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            mat = cv.imread('./screencap.png')
            template = cv.imread(get_image_path(image_name))
            result = cv.matchTemplate(mat, template, cv.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv.minMaxLoc(result)

            print(f"[{current_time}] Analyzing image {image_name} - {max_val}")

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

    def create_first_unit(self):
        self.touch_screen(self.first_troop['x'], self.first_troop['y'])

    def check_if_is_in_battle(self):
        is_in_battle = self.analyze_image('is-in-battle.png')
        return bool(is_in_battle)

    def check_if_is_on_menu(self):
        is_on_menu = self.analyze_image('market-menu-button.png')
        return bool(is_on_menu)

    def handle_battle_state(self):
        self.create_first_unit()

        close_battle_button = self.analyze_image('close-battle-button.png')
        self.is_in_battle = self.check_if_is_in_battle()

        if close_battle_button:
            self.exit_battle()
            self.is_in_battle = False

    def exit_battle(self):
        close_battle_button = self.analyze_image('close-battle-button.png')

        if close_battle_button:
            self.touch_screen(close_battle_button['x'], close_battle_button['y'])
            time.sleep(1)

        stuck_button = self.analyze_image('are-you-stuck-button.png')
        if stuck_button:
            self.touch_screen(stuck_button['x'], stuck_button['y'])

    def handle_menu_state(self):
        stuck_button = self.analyze_image('are-you-stuck-button.png')
        if stuck_button:
            self.touch_screen(stuck_button['x'], stuck_button['y'])

        self.upgrade_and_start_battle()

    def upgrade_and_start_battle(self):
        if self.should_upgrade_production:
            self.touch_screen(self.upgrade_menu['x'], self.upgrade_menu['y'])

            wait(600)
            self.device.shell(f"input touchscreen swipe {self.upgrade_production['x']} {self.upgrade_production['y']} {self.upgrade_production['x']} {self.upgrade_production['y']} 3000")
            wait(600)

        buttonToUser = None

        start_time = time.time()
        while not buttonToUser and time.time() - start_time < 10:
            self.touch_screen(self.battle_menu['x'], self.battle_menu['y'])
            battle_button = self.analyze_image('start-battle-button.png')
            battle_brown_button = self.analyze_image('start-battle-brown-button.png')

            if battle_brown_button:
                buttonToUser = battle_brown_button
            elif battle_button:
                buttonToUser = battle_button

        # Add a check to ensure buttonToUser is not None
        if buttonToUser is None:
            print("Could not find battle button")
            return

        start_time = time.time()
        while not self.is_in_battle and time.time() - start_time < 10:
            self.touch_screen(buttonToUser['x'], buttonToUser['y'])
            self.is_in_battle = self.check_if_is_in_battle()
            

    # def read_number_from_screen(self, region=None):
    #     image = Image.open('./screencap.png')

    #     if region:
    #         image = image.crop(region)
    #     text = pytesseract.image_to_string(image)

    #     print(text, 'aber', region)

    #     return text.strip()

    def run(self):

        while True:
            # self.read_number_from_screen(region=(822, 1273, 992, 1333))
            if self.pause:
                continue

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
                close_battle_button = self.analyze_image('close-battle-button.png')

                if close_battle_button:
                    self.exit_battle()


if __name__ == "__main__":
    try:
        game_automation = GameAutomation()
        if game_automation.initialize():
            game_automation.run()
    except Exception as e:
        print(e)
