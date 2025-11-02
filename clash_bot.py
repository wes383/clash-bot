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
TROPHY_THRESHOLD = 15000
# 奖杯数字区域矩形 (左上角x, 左上角y, 右下角x, 右下角y)
TROPHY_CROP_BOX = (600, 530, 780, 590)

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
        device = devices[0];
        logging.info(f"成功连接到设备: {device.serial}");
        return device
    except Exception as e:
        logging.error(f"连接ADB服务时发生错误: {e}");
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
    """从屏幕截图中读取奖杯数"""
    try:
        x1, y1, x2, y2 = crop_box
        trophy_img = screen[y1:y2, x1:x2]

        gray_img = cv2.cvtColor(trophy_img, cv2.COLOR_BGR2GRAY)

        _, binary_img = cv2.threshold(gray_img, 190, 255, cv2.THRESH_BINARY)

        pil_img = Image.fromarray(binary_img)

        config = '--psm 7 -c tessedit_char_whitelist=0123456789'
        text = pytesseract.image_to_string(pil_img, config=config)

        trophy_count = int(text.strip())
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
                    tap(device, card_xy[0], card_xy[1]);
                    time.sleep(0.2)
                    tap(device, DEPLOY_POINT_XY[0], DEPLOY_POINT_XY[1]);
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
                match_started = True;
                break
        time.sleep(1)
    if match_started:
        play_game(device, should_play_cards=play_cards_this_round)
    else:
        logging.error("等待超时，未能进入对战界面。")


def main():
    device = connect_device()
    if not device: time.sleep(10); return

    logging.info("已启动")
    while True:
        screen = take_screenshot(device)
        if screen is None: time.sleep(LOOP_INTERVAL); continue

        found_ok, loc = find_image(screen, TEMPLATE_OK_BUTTON)
        if found_ok:
            template = cv2.imread(TEMPLATE_OK_BUTTON);
            h, w, _ = template.shape
            tap(device, loc[0] + w // 2, loc[1] + h // 2)
            logging.info("点击'确定'，返回主界面...")
            time.sleep(5);
            continue

        found_battle, loc = find_image(screen, TEMPLATE_BATTLE_BUTTON)
        if found_battle:
            trophies = read_trophies(screen, TROPHY_CROP_BOX)
            should_play = True  # 默认下牌
            if trophies is not None:  # 如果成功读到数字
                if trophies > TROPHY_THRESHOLD:
                    logging.warning(f"当前奖杯 {trophies} > {TROPHY_THRESHOLD}，下一局将不下牌。")
                    should_play = False
                else:
                    logging.info(f"当前奖杯 {trophies} <= {TROPHY_THRESHOLD}，下一局将正常下牌。")

            template = cv2.imread(TEMPLATE_BATTLE_BUTTON);
            h, w, _ = template.shape
            tap(device, loc[0] + w // 2, loc[1] + h // 2)
            logging.info("在主界面点击'对战'...")

            wait_for_match_and_play(device, play_cards_this_round=should_play)
            continue

        logging.info("未找到'确定'或'对战'按钮，3秒后重试...")
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()
