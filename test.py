import time
import logging
import os
from CloudflareBypasser import CloudflareBypasser
from DrissionPage import ChromiumPage, ChromiumOptions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('cloudflare_bypass.log', mode='w')
    ]
)


def get_chromium_options(browser_path: str, arguments) -> ChromiumOptions:
    """
    Configures and returns Chromium options.

    :param browser_path: Path to the Chromium browser executable.
    :param arguments: List of arguments for the Chromium browser.
    :return: Configured ChromiumOptions instance.
    """
    options = ChromiumOptions().auto_port()
    options.set_paths(browser_path=browser_path)
    # 管理员/root环境下的必要设置
    options.set_argument("--no-sandbox")
    options.add_extension("turnstilePatch")
    options.set_argument('--disable-dev-shm-usage')
    options.set_argument('--disable-gpu')  # Linux环境可能需要
    options.set_argument('--disable-software-rasterizer')
    #options.set_argument('--lang=en-US')  # 设置浏览器界面语言
    #options.set_argument('--accept-languages=en-US,en')  # 设置HTTP请求头语言偏好
    #options.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3")
    for argument in arguments:
        options.set_argument(argument)
    return options


def main():
    browser_path = os.getenv('CHROME_PATH', "/usr/bin/chromium")

    # Windows Example
    # browser_path = os.getenv('CHROME_PATH', r"C:/Program Files/Google/Chrome/Application/chrome.exe")

    # Arguments to make the browser better for automation and less detectable.
    arguments = [
        # "-no-first-run",
        # "-force-color-profile=srgb",
        # "-metrics-recording-only",
        # "-password-store=basic",
        # "-use-mock-keychain",
        # "-export-tagged-pdf",
        # "-no-default-browser-check",
        # "-disable-background-mode",
        # "-enable-features=NetworkService,NetworkServiceInProcess,LoadCryptoTokenExtension,PermuteTLSExtensions",
        # "-disable-features=FlashDeprecationWarning,EnablePasswordsAccountStorage",
        # "-deny-permission-prompts",
        # "--lang=en-US",
    ]

    options = get_chromium_options(browser_path, arguments)

    # Initialize the browser
    driver = ChromiumPage(addr_or_opts=options)
    try:
        logging.info('Navigating to the demo page.')
        driver.get('https://nopecha.com/demo/cloudflare')

        # Where the bypass starts
        logging.info('Starting Cloudflare bypass.')
        cf_bypasser = CloudflareBypasser(driver)

        # If you are solving an in-page captcha (like the one here: https://seleniumbase.io/apps/turnstile), use cf_bypasser.click_verification_button() directly instead of cf_bypasser.bypass().
        # It will automatically locate the button and click it. Do your own check if needed.

        cf_bypasser.bypass()

        logging.info("Enjoy the content!")
        logging.info("Title of the page: %s", driver.title)

        # Sleep for a while to let the user see the result if needed
        time.sleep(5)
    except Exception as e:
        logging.error("An error occurred: %s", str(e))
    finally:
        logging.info('Closing the browser.')
        driver.quit()


if __name__ == '__main__':
    main()

