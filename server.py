import re
import os
from urllib.parse import urlparse
import time
import threading
import asyncio
from CloudflareBypasser import CloudflareBypasser
import platform
from DrissionPage import ChromiumPage, ChromiumOptions
from fastapi import FastAPI, HTTPException,Depends
from pydantic import BaseModel
from typing import Dict
from starlette.status import HTTP_403_FORBIDDEN
from pyvirtualdisplay import Display
import uvicorn
import atexit
import argparse
from concurrent.futures import ThreadPoolExecutor

from utils import get_browser_path, logging, LOG_LANG
from proxy_manager import start_proxy_with_auth, stop_proxy

# 环境变量配置
SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))
PASSWORD = os.getenv("PASSWORD", "gua12345")
MAX_BROWSERS = int(os.getenv("MAX_BROWSERS", 2))

# 日志初始化
if LOG_LANG == "zh":
    logging.info(f"当前访问密码: {PASSWORD}")
    logging.info(f"最大并发浏览器数量: {MAX_BROWSERS}")
else:
    logging.info(f"Current password: {PASSWORD}")
    logging.info(f"Maximum concurrent browsers: {MAX_BROWSERS}")

# 浏览器参数
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
    "--accept-languages=en-US,en",
    "--window-size=512,512",
]

# 确定浏览器路径
browser_path = os.getenv("CHROME_PATH", "")
if not browser_path:
    logging.warning("未设置CHROME_PATH环境变量")
    browser_path = get_browser_path()
    if not browser_path:
        logging.error("无法自动定位浏览器路径")
        raise ValueError("无法自动定位浏览器路径")
    else:
        logging.info(f"自动定位到浏览器路径: {browser_path}")

app = FastAPI()

# 线程池
thread_pool = ThreadPoolExecutor(max_workers=MAX_BROWSERS)

# 浏览器池管理类
class BrowserPoolManager:
    def __init__(self, max_browsers=MAX_BROWSERS):
        self.max_browsers = max_browsers
        self.active_browsers = 0
        self.browser_lock = threading.Lock()
        self.browser_semaphore = threading.BoundedSemaphore(max_browsers)
        self.active_proxies = set()
        self.proxy_lock = threading.Lock()

    def acquire_browser(self):
        result = self.browser_semaphore.acquire(blocking=False)
        if result:
            with self.browser_lock:
                self.active_browsers += 1
                logging.info(f"[{time.time()}] 当前活跃浏览器数: {self.active_browsers}/{self.max_browsers}")
        else:
            logging.warning(f"[{time.time()}] 浏览器资源已达上限，无法获取新资源")
        return result

    def release_browser(self):
        with self.browser_lock:
            if self.active_browsers > 0:
                self.active_browsers -= 1
                logging.info(f"[{time.time()}] 释放浏览器资源，当前活跃浏览器数: {self.active_browsers}/{self.max_browsers}")
                self.browser_semaphore.release()
            else:
                logging.warning(f"[{time.time()}] 尝试释放不存在的浏览器资源")

    def register_proxy(self, proxy):
        if proxy:
            with self.proxy_lock:
                self.active_proxies.add(proxy)
                logging.info(f"[{time.time()}] 注册代理: {proxy}, 当前活跃代理数: {len(self.active_proxies)}")

    def unregister_proxy(self, proxy):
        if proxy:
            with self.proxy_lock:
                if proxy in self.active_proxies:
                    self.active_proxies.remove(proxy)
                    logging.info(f"[{time.time()}] 注销代理: {proxy}, 当前活跃代理数: {len(self.active_proxies)}")
                else:
                    logging.warning(f"[{time.time()}] 尝试注销不存在的代理: {proxy}")

    def cleanup(self):
        logging.info(f"[{time.time()}] 执行浏览器池清理...")
        with self.proxy_lock:
            for proxy in list(self.active_proxies):
                try:
                    stop_proxy(proxy)
                    self.active_proxies.remove(proxy)
                    logging.info(f"[{time.time()}] 清理代理: {proxy}")
                except Exception as e:
                    logging.error(f"[{time.time()}] 清理代理失败: {proxy}, 错误: {str(e)}")

    def get_status(self):
        with self.browser_lock:
            return {
                "active_browsers": self.active_browsers,
                "max_browsers": self.max_browsers,
                "available_slots": self.max_browsers - self.active_browsers
            }

    def can_acquire_browser(self):
        with self.browser_lock:
            return self.active_browsers < self.max_browsers

browser_pool = BrowserPoolManager()

# 请求结果类
class RequestResult:
    def __init__(self):
        self.result = None
        self.error = None
        self.event = asyncio.Event()

    def set_result(self, result):
        self.result = result
        self.event.set()

    def set_error(self, error):
        self.error = error
        self.event.set()

# 清理资源
def cleanup_resources():
    logging.info(f"[{time.time()}] 程序退出，清理资源...")
    browser_pool.cleanup()
    thread_pool.shutdown(wait=False)

atexit.register(cleanup_resources)

# Pydantic 模型
class CookieResponse(BaseModel):
    cookies: Dict[str, str]
    user_agent: str

class PoolStatus(BaseModel):
    active_browsers: int
    max_browsers: int
    available_slots: int

# 密码验证
async def verify_password(password: str):
    if password != PASSWORD:
        logging.warning(f"[{time.time()}] 密码验证失败: {password}")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid password")
    return password

# URL 安全检查
def is_safe_url(url: str) -> bool:
    parsed_url = urlparse(url)
    ip_pattern = re.compile(
        r"^(127\.0\.0\.1|localhost|0\.0\.0\.0|::1|10\.\d+\.\d+\.\d+|172\.1[6-9]\.\d+\.\d+|172\.2[0-9]\.\d+\.\d+|172\.3[0-1]\.\d+\.\d+|192\.168\.\d+\.\d+)$"
    )
    hostname = parsed_url.hostname
    if (hostname and ip_pattern.match(hostname)) or parsed_url.scheme == "file":
        return False
    return True

# Cloudflare 绕过函数
def bypass_cloudflare(
        url: str,
        retries: int,
        log: bool,
        turnstile: bool = False,
        proxy: str = None,
        user_agent: str = None
) -> tuple[ChromiumPage, str | None]:
    logging.info(f"[{time.time()}] 开始绕过Cloudflare验证: {url}")
    options = ChromiumOptions().auto_port()
    for argument in arguments:
        options.set_argument(argument)
    options.add_extension("turnstilePatch")
    options.add_extension("cloudflare_ua_patch")
    options.set_paths(browser_path=browser_path)
    options.headless(os.getenv("HEADLESS", False))
    options.ignore_certificate_errors(on_off=True)
    if user_agent:
        options.set_user_agent(user_agent)
    else:
        options.set_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

    if platform.system() == "Linux":
        logging.info(f"[{time.time()}] 检测到Linux系统，应用特殊配置")
        options.set_argument("--no-sandbox")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-gpu")
        options.set_argument("--disable-software-rasterizer")

    no_auth_proxy = None
    if proxy:
        logging.info(f"[{time.time()}] 使用代理: {proxy}")
        if "@" in proxy:
            no_auth_proxy = start_proxy_with_auth(proxy)
        else:
            no_auth_proxy = proxy
        options.set_proxy(no_auth_proxy)
        browser_pool.register_proxy(no_auth_proxy)

    driver = None
    try:
        driver = ChromiumPage(addr_or_opts=options)
        driver.get(url)
        cf_bypasser = CloudflareBypasser(driver, retries, log)
        if turnstile:
            logging.info(f"[{time.time()}] 开始绕过turnstile验证")
            cf_bypasser.bypass_turnstile()
        else:
            logging.info(f"[{time.time()}] 开始绕过普通验证")
            cf_bypasser.bypass()
        return driver, no_auth_proxy
    except Exception as e:
        logging.error(f"[{time.time()}] 绕过Cloudflare验证失败: {str(e)}")
        if driver:
            driver.quit()
        if no_auth_proxy:
            browser_pool.unregister_proxy(no_auth_proxy)
            stop_proxy(no_auth_proxy)
        raise e

# 处理 cookies 请求
def process_cookies_request(
        url: str,
        retries: int,
        proxy: str,
        user_agent: str,
        result_obj: RequestResult
):
    logging.info(f"[{time.time()}] 任务开始执行")
    no_auth_proxy = None
    driver = None

    try:
        driver, no_auth_proxy = bypass_cloudflare(url, retries, True, False, proxy, user_agent)
        cookies = {cookie.get("name", ""): cookie.get("value", " ") for cookie in driver.cookies()}
        user_agent_value = driver.user_agent
        driver.quit()
        driver = None
        logging.info(f"[{time.time()}] 成功获取cookies")
        result_obj.set_result(CookieResponse(cookies=cookies, user_agent=user_agent_value))
    except Exception as e:
        logging.error(f"[{time.time()}] 获取cookies失败: {str(e)}")
        result_obj.set_error(str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logging.error(f"[{time.time()}] 关闭浏览器失败: {str(e)}")
        browser_pool.release_browser()
        if no_auth_proxy:
            try:
                browser_pool.unregister_proxy(no_auth_proxy)
                if stop_proxy(no_auth_proxy):
                    logging.info(f"[{time.time()}] 成功结束本地代理")
                else:
                    logging.error(f"[{time.time()}] 结束本地代理失败")
            except Exception as e:
                logging.error(f"[{time.time()}] 清理代理资源失败: {str(e)}")

# 处理 turnstile 请求
def process_turnstile_request(
        url: str,
        retries: int,
        proxy: str,
        user_agent: str,
        result_obj: RequestResult
):
    logging.info(f"[{time.time()}] 任务开始执行")
    no_auth_proxy = None
    driver = None

    try:
        driver, no_auth_proxy = bypass_cloudflare(url, retries, True, True, proxy, user_agent)
        retry_interval = 2
        cf_clearance = None
        retry_count = 0
        turnstile_token = ""
        while retry_count < retries:
            cookies = driver.cookies()
            for cookie in cookies:
                if cookie["name"] == "cf_clearance":
                    cf_clearance = cookie["value"]
                    break
            try:
                turnstile = driver.ele("tag:input@name=cf-turnstile-response")
                turnstile_token = turnstile.value
            except Exception as e:
                logging.error(f"[{time.time()}] 获取turnstile_token时出错: {e}")
            if cf_clearance and turnstile_token:
                break
            retry_count += 1
            time.sleep(retry_interval)
            logging.info(f"[{time.time()}] 正在第{retry_count}次尝试获取cf_clearance和turnstile_token...")
        if not cf_clearance:
            logging.error(f"[{time.time()}] 未能获取到cf_clearance cookie和turnstile_token")
            result_obj.set_error("未能获取到cf_clearance cookie和turnstile_token")
            return
        cookies = {cookie.get("name", ""): cookie.get("value", " ") for cookie in driver.cookies()}
        cookies["turnstile_token"] = turnstile_token
        user_agent_value = driver.user_agent
        driver.quit()
        driver = None
        logging.info(f"[{time.time()}] 成功获取turnstile cookies")
        result_obj.set_result(CookieResponse(cookies=cookies, user_agent=user_agent_value))
    except Exception as e:
        logging.error(f"[{time.time()}] 获取turnstile cookies失败: {str(e)}")
        result_obj.set_error(str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logging.error(f"[{time.time()}] 关闭浏览器失败: {str(e)}")
        browser_pool.release_browser()
        if no_auth_proxy:
            try:
                browser_pool.unregister_proxy(no_auth_proxy)
                if stop_proxy(no_auth_proxy):
                    logging.info(f"[{time.time()}] 成功结束本地代理")
                else:
                    logging.error(f"[{time.time()}] 结束本地代理失败")
            except Exception as e:
                logging.error(f"[{time.time()}] 清理代理资源失败: {str(e)}")

# Cookies 端点（异步优化）
@app.get("/{password}/cookies", response_model=CookieResponse)
async def get_cookies(
        password: str = Depends(verify_password),
        url: str = None,
        retries: int = 5,
        proxy: str = None,
        user_agent: str = None
) -> CookieResponse:
    logging.info(f"[{time.time()}] 收到cookies请求: {url}")
    if not is_safe_url(url):
        logging.warning(f"[{time.time()}] 不安全的URL: {url}")
        raise HTTPException(status_code=400, detail="Invalid URL")

    # 在提交任务前尝试获取浏览器资源
    if not browser_pool.acquire_browser():
        logging.warning(f"[{time.time()}] 浏览器资源已达上限，拒绝新请求")
        raise HTTPException(status_code=503, detail="浏览器资源已达上限，无法处理请求")

    result = RequestResult()
    logging.info(f"[{time.time()}] 提交任务到线程池")
    future = thread_pool.submit(
        process_cookies_request,
        url,
        retries,
        proxy,
        user_agent,
        result
    )
    try:
        await asyncio.wait_for(result.event.wait(), timeout=60)
        if result.error:
            raise HTTPException(status_code=503, detail=result.error)
        return result.result
    except asyncio.TimeoutError:
        logging.error(f"[{time.time()}] 请求超时")
        raise HTTPException(status_code=504, detail="请求超时")
    finally:
        # 如果任务未完成，释放资源
        if not result.event.is_set():
            browser_pool.release_browser()

# Turnstile 端点（异步优化）
@app.get("/{password}/turnstile", response_model=CookieResponse)
async def get_turnstile_cookies(
        password: str = Depends(verify_password),
        url: str = None,
        retries: int = 5,
        proxy: str = None,
        user_agent: str = None
) -> CookieResponse:
    logging.info(f"[{time.time()}] 收到turnstile请求: {url}")
    if not is_safe_url(url):
        logging.warning(f"[{time.time()}] 不安全的URL: {url}")
        raise HTTPException(status_code=400, detail="Invalid URL")

    # 在提交任务前尝试获取浏览器资源
    if not browser_pool.acquire_browser():
        logging.warning(f"[{time.time()}] 浏览器资源已达上限，拒绝新请求")
        raise HTTPException(status_code=503, detail="浏览器资源已达上限，无法处理请求")

    result = RequestResult()
    logging.info(f"[{time.time()}] 提交任务到线程池")
    future = thread_pool.submit(
        process_turnstile_request,
        url,
        retries,
        proxy,
        user_agent,
        result
    )
    try:
        await asyncio.wait_for(result.event.wait(), timeout=60)
        if result.error:
            raise HTTPException(status_code=503, detail=result.error)
        return result.result
    except asyncio.TimeoutError:
        logging.error(f"[{time.time()}] 请求超时")
        raise HTTPException(status_code=504, detail="请求超时")
    finally:
        # 如果任务未完成，释放资源
        if not result.event.is_set():
            browser_pool.release_browser()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloudflare bypass API")
    parser.add_argument("--nolog", action="store_true", help="禁用日志")
    parser.add_argument("--headless", action="store_true", help="以无头模式运行")
    parser.add_argument("--max-browsers", type=int, default=MAX_BROWSERS, help="最大并发浏览器数量")
    parser.add_argument("--max-workers", type=int, default=MAX_BROWSERS, help="最大工作线程数量")
    args = parser.parse_args()

    browser_pool.max_browsers = args.max_browsers
    thread_pool.shutdown(wait=True)
    thread_pool = ThreadPoolExecutor(max_workers=args.max_workers)

    display = None
    if args.headless:
        logging.info(f"[{time.time()}] 启用无头模式")
        display = Display(visible=0, size=(1920, 1080))
        display.start()

        def cleanup_display():
            if display:
                logging.info(f"[{time.time()}] 清理Display资源")
                display.stop()

        atexit.register(cleanup_display)

    log = not args.nolog
    if args.nolog:
        logging.info(f"[{time.time()}] 禁用日志")

    logging.info(
        f"[{time.time()}] 启动服务器，端口: {SERVER_PORT}, 最大并发浏览器数: {browser_pool.max_browsers}, 最大工作线程数: {args.max_workers}"
    )
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)