# Clash-Bot

本脚本仅用于学习用途，试图通过第三方软件获取不正当优势的游戏账号可能面临永久封禁的处罚。详见 [SUPERCELL SAFE AND FAIR PLAY POLICY](https://supercell.com/en/safe-and-fair-play/)。

## 安装

1.  **克隆项目**

    ```bash
    git clone https://github.com/wes383/clash-bot.git
    cd clash-bot
    ```

2.  **安装依赖**

    确保已安装 Python 3.x，然后运行以下命令安装所需的库：
    ```bash
    pip install -r requirements.txt
    ```

3.  **安装 Tesseract OCR**

    此项目需要 Tesseract OCR。请从 [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html) 下载并安装。

    安装后，请确保将 Tesseract 的安装路径正确配置在 `clash_bot.py` 文件中：
    ```python
    # Tesseract 安装路径
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    ```

4.  **配置和启用 ADB**

    推荐使用安卓模拟器，将分辨率改为纵向 1440*2560，并打开 ADB 调试。
    
    本测试使用的模拟器为 [MuMuPlayer](https://www.mumuplayer.com/)。

## 使用方法

1.  **连接设备**

    确保安卓设备已通过 ADB 连接并被正确识别。可以通过以下命令检查：
    ```bash
    adb devices
    ```

2.  **运行脚本**

    运行 `clash_bot.py`：
    ```bash
    python clash_bot.py
    ```

## 配置

可以在 `clash_bot.py` 文件的开头部分根据需求修改以下参数：

- `TROPHY_THRESHOLD`: 奖杯阈值。当奖杯数高于此值，机器人不会下牌。
- `TROPHY_CROP_BOX`: 奖杯数在屏幕上的识别区域。
- `CARD_SLOTS_XY`: 四个卡牌在屏幕上的坐标。
- `DEPLOY_POINT_XY`: 出牌时在地图上点击的坐标。

## 注意事项

- 运行前请确保每日奖励已经领完，保证对战结束后点击确定可以回到主界面。
- 请确保游戏语言为中文，因为图像识别模板是基于中文版界面制作的。或者自行更改图像模板。
- 脚本的稳定性和识别率可能会受到设备分辨率、游戏版本更新等因素的影响。
