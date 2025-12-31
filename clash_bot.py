import cv2
import numpy as np
from ppadb.client import Client as AdbClient
import time
import logging
import math
import pytesseract
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
SIMILARITY_THRESHOLD = 0.8
LOOP_INTERVAL = 3

# Tesseract 安装路径
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# 奖杯阈值
TROPHY_THRESHOLD = 5200
# 奖杯数字区域矩形 (左上角x, 左上角y, 右下角x, 右下角y)
TROPHY_CROP_BOX = (600, 530, 770, 590)

CARD_SLOTS_XY = [(451, 2276), (729, 2276), (1000, 2276), (1235, 2276)]
DEPLOY_POINT_XY = (1300, 1873)
ELIXIR_CHECK_XY = (1044, 2510)
EXPECTED_ELIXIR_COLOR_BGR = (210, 32, 203)

TEMPLATE_BATTLE_BUTTON = 'assets/battle_button.png'
TEMPLATE_OK_BUTTON = 'assets/ok_button.png'
TEMPLATE_AGAIN_BUTTON = 'assets/again_button.png'
TEMPLATE_ELIXIR_ANCHOR = 'assets/elixir_anchor.png'


def connect_device():
    try:
        client = AdbClient(host="127.0.0.1", port=5037)
        devices = client.devices()
        if not devices: return None
        device = devices[0]
        logging.info(f"成功连接到设备: {device.serial}")
        return device
    except Exception as e:
        logging.error(f"连接ADB服务时发生错误: {e}")
        return None


def take_screenshot(device):
    try:
        result = device.screencap()
        return cv2.imdecode(np.frombuffer(result, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def find_image(screen, template_path, threshold=0.9):
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None: return False, None
    res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return max_val >= threshold, max_loc


def tap(device, x, y):
    device.shell(f"input tap {x} {y}")

def is_elixir_sufficient(screen, check_coords, expected_bgr, tolerance=50):
    try:
        b, g, r = screen[check_coords[1], check_coords[0]]
        expected_b, expected_g, expected_r = expected_bgr
        distance = math.sqrt((int(b) - expected_b) ** 2 + (int(g) - expected_g) ** 2 + (int(r) - expected_r) ** 2)
        return distance < tolerance
    except IndexError:
        return False

def read_trophies(screen, crop_box):
    try:
        x1, y1, x2, y2 = crop_box
        trophy_img = screen[y1:y2, x1:x2]

        gray = cv2.cvtColor(trophy_img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        pil_img = Image.fromarray(binary)

        config = '--psm 7 -c tessedit_char_whitelist=0123456789'
        text = pytesseract.image_to_string(pil_img, config=config)

        text = text.strip()
        import re
        digits = re.findall(r'\d+', text)

        if not digits:
            logging.error(f"OCR 未识别到数字，原始结果: '{text}'")
            return None

        trophy_count = int(digits[0])
        logging.info(f"成功识别奖杯数: {trophy_count}")
        return trophy_count

    except Exception as e:
        logging.error(f"读取奖杯数失败: {e}")
        return None

def play_game(device, should_play_cards=True):
    """对战逻辑"""
    if not should_play_cards:
        logging.warning("奖杯数高于阈值，本局将不下牌。")

    logging.info("====== 进入对战 ======")
    match_start_time = time.time()
    MAX_MATCH_DURATION = 300
    while True:
        if time.time() - match_start_time > MAX_MATCH_DURATION:
            logging.warning("对战超时，自动退出。")
            break
        screen = take_screenshot(device)
        if screen is None: time.sleep(1); continue

        found_ok, _ = find_image(screen, TEMPLATE_OK_BUTTON)
        found_again, _ = find_image(screen, TEMPLATE_AGAIN_BUTTON)
        if found_ok or found_again:
            logging.info("检测到对局结束按钮，正常退出对战。")
            break

        if should_play_cards:
            if is_elixir_sufficient(screen, ELIXIR_CHECK_XY, EXPECTED_ELIXIR_COLOR_BGR):
                logging.info("圣水已满，开始连续下牌...")
                for card_xy in CARD_SLOTS_XY:
                    tap(device, card_xy[0], card_xy[1])
                    time.sleep(0.2)
                    tap(device, DEPLOY_POINT_XY[0], DEPLOY_POINT_XY[1])
                    time.sleep(2)
                time.sleep(2)
            else:
                time.sleep(1)
        else:
            time.sleep(5)

    logging.info("====== 对战逻辑执行完毕 ======")


def wait_for_match_and_play(device, play_cards_this_round):
    logging.info("正在等待对战开始...")
    time.sleep(5)
    match_started = False
    for i in range(15):
        logging.info(f"  -> 寻找对战界面... (第 {i + 1} 次尝试)")
        screen = take_screenshot(device)
        if screen is not None:
            is_in_battle, _ = find_image(screen, TEMPLATE_ELIXIR_ANCHOR)
            if is_in_battle:
                match_started = True
                break
        time.sleep(1)
    if match_started:
        play_game(device, should_play_cards=play_cards_this_round)
    else:
        logging.error("等待超时，未能进入对战界面。")


def main():
    device = connect_device()
    if not device:
        time.sleep(10)
        return

    logging.info("已启动")

    unknown_state_counter = 0
    FALLBACK_CLICK_THRESHOLD = 2

    while True:
        screen = take_screenshot(device)
        if screen is None:
            time.sleep(LOOP_INTERVAL)
            continue

        # --- 处理“确定”按钮 ---
        found_ok, loc = find_image(screen, TEMPLATE_OK_BUTTON)
        if found_ok:
            unknown_state_counter = 0
            template = cv2.imread(TEMPLATE_OK_BUTTON)
            h, w, _ = template.shape
            tap(device, loc[0] + w // 2, loc[1] + h // 2)
            logging.info("点击'确定'，返回主界面...")
            time.sleep(8)
            continue

        # --- 处理“对战”按钮 ---
        found_battle, loc = find_image(screen, TEMPLATE_BATTLE_BUTTON)
        if found_battle:
            time.sleep(3)
            unknown_state_counter = 0

            trophies = read_trophies(screen, TROPHY_CROP_BOX)
            should_play = True
            if trophies is not None and trophies > TROPHY_THRESHOLD:
                logging.warning(f"当前奖杯 {trophies} > {TROPHY_THRESHOLD}，下一局将不下牌。")
                should_play = False

            template = cv2.imread(TEMPLATE_BATTLE_BUTTON)
            h, w, _ = template.shape
            tap(device, loc[0] + w // 2, loc[1] + h // 2)
            logging.info("在主界面点击'对战'...")
            wait_for_match_and_play(device, play_cards_this_round=should_play)
            continue

        # --- 处理未知界面 ---
        unknown_state_counter += 1
        logging.warning(
            f"未找到可识别目标，等待3秒... (连续未知状态: {unknown_state_counter}/{FALLBACK_CLICK_THRESHOLD})")
        time.sleep(LOOP_INTERVAL)

        if unknown_state_counter >= FALLBACK_CLICK_THRESHOLD:
            logging.error(f"已连续 {unknown_state_counter} 次处于未知状态，尝试执行盲点回退操作！")
            fallback_x, fallback_y = (725, 2470)
            tap(device, fallback_x, fallback_y)
            logging.info(f"已点击回退坐标 ({fallback_x}, {fallback_y})，等待3秒让界面刷新...")
            unknown_state_counter = 0
            time.sleep(3)


if __name__ == "__main__":
    main()
