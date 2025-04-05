import time
from DrissionPage import ChromiumPage
import os
import platform
import logging

# 环境变量配置
LOG_LANG = os.getenv("LOG_LANG", "zh")  # 日志语言 zh/en

# 定义日志颜色
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'INFO': '\033[94m',  # 蓝色
        'WARNING': '\033[93m',  # 黄色
        'ERROR': '\033[91m',  # 红色
        'CRITICAL': '\033[91m',  # 红色
        'DEBUG': '\033[92m',  # 绿色
        'RESET': '\033[0m'  # 重置颜色
    }

    def format(self, record):
        log_message = super().format(record)
        if record.levelname in self.COLORS:
            return f"{self.COLORS[record.levelname]}{log_message}{self.COLORS['RESET']}"
        return log_message

# 配置日志记录
colored_formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s')
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler()
console_handler.setFormatter(colored_formatter)

file_handler = logging.FileHandler('cloudflare_bypass.log', mode='w')
file_handler.setFormatter(file_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)


def get_browser_path():
    """自动获取系统中已安装的浏览器路径"""
    system = platform.system()

    if system == "Windows":
        paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif system == "Linux":
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/firefox",
            "/snap/bin/chromium",
        ]
    elif system == "Darwin":  # macOS
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            "/Applications/Safari.app/Contents/MacOS/Safari",
        ]
    else:
        return None
    # 返回第一个存在的浏览器路径
    for path in paths:
        if os.path.exists(path):
            return path

    return None


class CloudflareBypasser:
    def __init__(self, driver: ChromiumPage, max_retries=-1, log=True):
        self.driver = driver
        self.max_retries = max_retries
        self.log = log
        self.log_lang = LOG_LANG  # 使用全局定义的LOG_LANG

    def search_recursively_shadow_root_with_iframe(self, ele):
        if ele.shadow_root:
            if ele.shadow_root.child().tag == "iframe":
                return ele.shadow_root.child()
        else:
            for child in ele.children():
                result = self.search_recursively_shadow_root_with_iframe(child)
                if result:
                    return result
        return None

    def search_recursively_shadow_root_with_cf_input(self, ele):
        if ele.shadow_root:
            if ele.shadow_root.ele("tag:input"):
                return ele.shadow_root.ele("tag:input")
        else:
            for child in ele.children():
                result = self.search_recursively_shadow_root_with_cf_input(child)
                if result:
                    return result
        return None

    def locate_cf_button(self):
        button = None
        eles = self.driver.eles("tag:input")
        for ele in eles:
            if "name" in ele.attrs.keys() and "type" in ele.attrs.keys():
                if "turnstile" in ele.attrs["name"] and ele.attrs["type"] == "hidden":
                    button = ele.parent().shadow_root.child()("tag:body").shadow_root("tag:input")
                    break

        if button:
            return button
        else:
            # If the button is not found, search it recursively
            self.log_message("基础搜索失败，正在递归查找按钮...")
            ele = self.driver.ele("tag:body")
            iframe = self.search_recursively_shadow_root_with_iframe(ele)
            if iframe:
                button = self.search_recursively_shadow_root_with_cf_input(iframe("tag:body"))
            else:
                self.log_message("未找到iframe，按钮搜索失败")
            return button

    def log_message(self, message):
        if self.log:
            if self.log_lang == "en":
                # 英文日志翻译
                translations = {
                    "基础搜索失败，正在递归查找按钮...": "Basic search failed. Searching for button recursively...",
                    "未找到iframe，按钮搜索失败": "Iframe not found. Button search failed",
                    "找到验证按钮，尝试点击...": "Verification button found. Attempting to click",
                    "未找到验证按钮": "Verification button not found",
                    "点击验证按钮时出错": "Error clicking verification button",
                    "检查页面标题时出错": "Error checking page title",
                    "超过最大重试次数，绕过失败": "Exceeded maximum retries. Bypass failed",
                    "尝试 {0}: 检测到验证页面，正在尝试绕过...": "Attempt {0}: Verification page detected. Trying to bypass...",
                    "成功绕过验证": "Bypass successful",
                    "绕过验证失败": "Bypass failed",
                    "成功绕过turnstile前的challenge验证": "Successfully bypassed challenge verification before turnstile",
                    "绕过turnstile前的challenge验证失败": "Failed to bypass challenge verification before turnstile",
                    "成功绕过turnstile验证": "Successfully bypassed turnstile verification",
                    "绕过turnstile验证失败": "Failed to bypass turnstile verification",
                    "检查turnstile时出错": "Error checking turnstile"
                }
                message = translations.get(message, message)
            logging.info(message)

    def click_verification_button(self):
        try:
            button = self.locate_cf_button()
            if button:
                self.log_message("找到验证按钮，尝试点击...")
                button.click()
            else:
                self.log_message("未找到验证按钮")
        except Exception as e:
            self.log_message(f"点击验证按钮时出错: {e}")

    def is_bypassed(self):
        try:
            title = self.driver.title.lower()
            return "just a moment" not in title
        except Exception as e:
            self.log_message(f"检查页面标题时出错: {e}")
            return False

    def is_turnstile(self):
        try:
            turnstile = self.driver.ele('tag:input@name=cf-turnstile-response')
            turnstile_token = turnstile.value
            if turnstile_token:
                # print(turnstile_token)
                return turnstile_token
            else:
                return ""
        except Exception as e:
            self.log_message(f"检查turnstile时出错: {e}")
            return ""

    def bypass(self):
        try_count = 0
        while not self.is_bypassed():
            if 0 < self.max_retries + 1 <= try_count:
                self.log_message("超过最大重试次数，绕过失败")
                break
            self.log_message(f"尝试 {try_count + 1}: 检测到验证页面，正在尝试绕过...")
            self.click_verification_button()
            try_count += 1
            time.sleep(2)
        if self.is_bypassed():
            self.log_message("成功绕过验证")
        else:
            self.log_message("绕过验证失败")

    def bypass_turnstile(self):
        try_count = 0
        while not self.is_bypassed():
            if 0 < self.max_retries + 1 <= try_count:
                self.log_message("超过最大重试次数，绕过失败")
                break
            self.log_message(f"尝试 {try_count + 1}: 检测到验证页面，正在尝试绕过...")
            self.click_verification_button()
            try_count += 1
            time.sleep(2)
        if self.is_bypassed():
            self.log_message("成功绕过turnstile前的challenge验证")
        else:
            self.log_message("绕过turnstile前的challenge验证失败")
        try_count = 0
        while not self.is_turnstile():
            if 0 < self.max_retries + 1 <= try_count:
                self.log_message("超过最大重试次数，绕过失败")
                break
            self.log_message(f"尝试 {try_count + 1}: 检测到验证页面，正在尝试绕过...")
            self.click_verification_button()
            try_count += 1
            time.sleep(2)
        if self.is_turnstile():
            self.log_message("成功绕过turnstile验证")
        else:
            self.log_message("绕过turnstile验证失败")