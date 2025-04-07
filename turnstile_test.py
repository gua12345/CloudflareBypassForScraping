import time
import logging
import os
import platform
from CloudflareBypasser import CloudflareBypasser
from DrissionPage import ChromiumPage, ChromiumOptions

from utils import get_browser_path, logging, LOG_LANG

def get_chromium_options(browser_path: str, arguments, user_agent: str = None) -> ChromiumOptions:
    """
    Configures and returns Chromium options.

    :param browser_path: Path to the Chromium browser executable.
    :param arguments: List of arguments for the Chromium browser.
    :return: Configured ChromiumOptions instance.
    """
    options = ChromiumOptions().auto_port()
    options.set_paths(browser_path=browser_path)
    # 基础配置，所有系统通用
    options.add_extension("turnstilePatch")
    options.add_extension("cloudflare_ua_patch")
    options.headless(False)
    
    # Linux 系统特殊配置
    if platform.system() == "Linux":
        options.set_argument("--auto-open-devtools-for-tabs")
        options.set_argument("--no-sandbox")
        options.set_argument('--disable-dev-shm-usage')
        options.set_argument('--disable-gpu')
        options.set_argument('--disable-software-rasterizer')

    
    if user_agent:
        options.set_user_agent(user_agent)
    else:
        options.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3")
    
    for argument in arguments:
        options.set_argument(argument)
    return options


def main():
    browser_path = os.getenv('CHROME_PATH', "")
    if not browser_path:
        if LOG_LANG == "zh":
            logging.warning("未设置CHROME_PATH环境变量,正在尝试自动查找浏览器路径")
        else:
            print("The CHROME_PATH environment variable is not set, attempting to automatically find the browser path")
        browser_path = get_browser_path()
        if not browser_path:
            if LOG_LANG == "zh":
                raise ValueError("无法自动定位浏览器路径")
            else:
                raise ValueError("Failed to locate browser path automatically")
        

    # Windows Example
    # browser_path = os.getenv('CHROME_PATH', r"C:/Program Files/Google/Chrome/Application/chrome.exe")

    # Arguments to make the browser better for automation and less detectable.
    arguments = [
        "-no-first-run",
        "-force-color-profile=srgb",
        "-metrics-recording-only",
        "-password-store=basic",
        "-use-mock-keychain",
        "-export-tagged-pdf",
        "-no-default-browser-check",
        "-disable-background-mode",
        "-enable-features=NetworkService,NetworkServiceInProcess,LoadCryptoTokenExtension,PermuteTLSExtensions",
        "-disable-features=FlashDeprecationWarning,EnablePasswordsAccountStorage",
        "-deny-permission-prompts",
        "-accept-lang=en-US",
        "--lang=en-US",
        '--accept-languages=en-US,en',
        "--window-size=512,512",
    ]

    # 测试自定义UA功能
    custom_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options = get_chromium_options(browser_path, arguments, user_agent=custom_ua)
    logging.info(f"Using custom User-Agent: {custom_ua}")

    # Initialize the browser
    driver = ChromiumPage(addr_or_opts=options)
    try:
        if LOG_LANG == "zh":
            logging.info('正在访问测试页面...')
        else:
            logging.info('Navigating to test page...')
        driver.get('https://accounts.x.ai/sign-in?redirect=grok-com')

        # Where the bypass starts
        if LOG_LANG == "zh":
            logging.info('开始绕过Cloudflare验证...')
        else:
            logging.info('Starting Cloudflare bypass...')
        cf_bypasser = CloudflareBypasser(driver)

        cf_bypasser.bypass_turnstile()

        if LOG_LANG == "zh":
            logging.info("验证成功，可以访问内容!")
        else:
            logging.info("Verification successful, content accessible!")
        if LOG_LANG == "zh":
            logging.info("页面标题: %s", driver.title)
        else:
            logging.info("Page title: %s", driver.title)
        logging.info("turnstile_token: %s", driver.ele('tag:input@name=cf-turnstile-response').value)

        # Sleep for a while to let the user see the result if needed
        time.sleep(5)
    except Exception as e:
        if LOG_LANG == "zh":
            logging.error("发生错误: %s", str(e))
        else:
            logging.error("Error occurred: %s", str(e))
    finally:
        if LOG_LANG == "zh":
            logging.info('正在关闭浏览器...')
        else:
            logging.info('Closing browser...')
        driver.quit()


if __name__ == '__main__':
    main()
