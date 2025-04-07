import os
import platform
import logging
import time

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

def check_cf_clearance(driver,retries=5):
    retry_interval = 1
    cf_clearance = ""
    retry_count = 0
    while retry_count < retries:
        cookies = driver.cookies()
        for cookie in cookies:
            if cookie['name'] == 'cf_clearance':
                cf_clearance = cookie['value']
                break
        if cf_clearance:
            return True
        retry_count += 1
        time.sleep(retry_interval)
        if LOG_LANG == "zh":
            logging.info(f"正在第{retry_count}次尝试获取cf_clearance...")
        else:
            logging.info(f"Attempt {retry_count}: Trying to get cf_clearance...")
    if not cf_clearance:
        logging.error("未能获取到cf_clearance cookie")
        return ""

def check_turnstile_token(driver):
    try:
        turnstile = driver.ele('tag:input@name=cf-turnstile-response')
        turnstile_token = turnstile.value
        if turnstile_token:
            logging.info(f"turnstile_token存在，已成功过盾")
            return turnstile_token
        else:
            logging.info(f"turnstile_token不存在，未成功过盾")
            return ""
    except Exception as e:
        logging.error(f"获取turnstile_token时出错: {e}")
        return ""