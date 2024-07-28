import cv2 as cv
import os
# import pytesseract
import time
import sys
from ppadb.client import Client as AdbClient
from utils.wait import wait
from utils.get_image_path import get_image_path
from datetime import datetime
# from PIL import Image

class GameAutomation:
    def __init__(self):
        self.client = AdbClient(host="127.0.0.1", port=5037)
        self.device = None
        self.current_image_loop = None
        self.loop_count = 0
        self.is_in_battle = False
        self.is_in_battle_count = 0
        self.pause = False
        self.should_upgrade_production = True

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

        import threading
        threading.Thread(target=key_handler, daemon=True).start()

    def screenshot(self):
        if not self.device:
            print("No device connected")
            return
        image = self.device.screencap()
        with open('./screencap.png', 'wb') as f:
            f.write(image)

    def analyze_image(self, image_name, refresh_image=False):
        if refresh_image or self.current_image_loop is None or self.current_image_loop != self.loop_count:
            self.screenshot()
            self.current_image_loop = self.loop_count

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time}] Analyzing image {image_name}")

        mat = cv.imread('./screencap.png')
        template = cv.imread(get_image_path(image_name))
        result = cv.matchTemplate(mat, template, cv.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv.minMaxLoc(result)

        match_threshold = 0.7
        if max_val < match_threshold:
            return None

        center_x = max_loc[0] + template.shape[1] // 2
        center_y = max_loc[1] + template.shape[0] // 2

        return {'x': center_x, 'y': center_y}

    def touch_screen(self, x, y):
        if not self.device:
            print("No device connected")
            return
        self.device.shell(f"input tap {x} {y}")

    def create_first_unit(self):
        self.touch_screen(self.first_troop['x'], self.first_troop['y'])

    def check_if_is_in_battle(self):
        self.screenshot()
        is_in_battle = self.analyze_image('is-in-battle.png')
        return bool(is_in_battle)

    def check_if_is_on_menu(self):
        self.screenshot()
        is_on_menu = self.analyze_image('market-menu-button.png')
        return bool(is_on_menu)

    def handle_battle_state(self):
        self.is_in_battle_count += 1
        self.create_first_unit()

        if self.is_in_battle_count >= 100:
            self.screenshot()
            close_battle_button = self.analyze_image('close-battle-button.png')
            self.is_in_battle = self.check_if_is_in_battle()

            if close_battle_button:
                self.exit_battle(close_battle_button)
                self.is_in_battle = False

            self.is_in_battle_count = 0

    def exit_battle(self, close_battle_button):
        while not self.check_if_is_on_menu():
            self.touch_screen(close_battle_button['x'], close_battle_button['y'])
            wait(500)

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
            wait(400)
            self.device.shell(f"input touchscreen swipe {self.upgrade_production['x']} {self.upgrade_production['y']} {self.upgrade_production['x']} {self.upgrade_production['y']} 3000")
            wait(400)

        self.touch_screen(self.battle_menu['x'], self.battle_menu['y'])
        self.screenshot()
        battle_button = self.analyze_image('start-battle-button.png', True)

        if battle_button:
            while not self.is_in_battle:
                self.touch_screen(battle_button['x'], battle_button['y'])
                self.is_in_battle = self.check_if_is_in_battle()

    # def read_number_from_screen(self, region=None):
    #     self.screenshot()
    #     image = Image.open('./screencap.png')

    #     if region:
    #         image = image.crop(region)
    #     text = pytesseract.image_to_string(image)

    #     print(text, 'aber', region)

    #     return text.strip()

    def run(self):
        start_time = time.time()

        while True:
            # self.read_number_from_screen(region=(822, 1273, 992, 1333))
            if self.pause:
                wait(100)
                continue

            if self.loop_count > 10000:
                end_time = time.time()
                print(f"Loop ran for {end_time - start_time} seconds")
                self.is_in_battle = self.check_if_is_in_battle()

            if self.is_in_battle:
                self.handle_battle_state()
                continue

            is_on_menu = self.check_if_is_on_menu()
            if is_on_menu:
                self.handle_menu_state()
            else:
                self.is_in_battle = True
                stuck_button = self.analyze_image('are-you-stuck-button.png')
                if stuck_button:
                    self.touch_screen(stuck_button['x'], stuck_button['y'])

            self.loop_count += 1

if __name__ == "__main__":
    try:
        game_automation = GameAutomation()
        if game_automation.initialize():
            game_automation.run()
    except Exception as e:
        print(e)
