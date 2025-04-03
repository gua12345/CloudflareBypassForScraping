import json
import logging
import re
import os
from urllib.parse import urlparse
import time
from CloudflareBypasser import CloudflareBypasser, get_browser_path
import platform
from DrissionPage import ChromiumPage, ChromiumOptions
from fastapi import FastAPI, HTTPException, Response, Depends
from pydantic import BaseModel
from typing import Dict
import argparse
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

from pyvirtualdisplay import Display
import uvicorn
import atexit

# 环境变量配置
SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))  # Docker模式端口
LOG_LANG = os.getenv("LOG_LANG", "zh")  # 日志语言 zh/en

# 设置访问密码(从环境变量读取，默认gua12345)
PASSWORD = os.getenv("PASSWORD", "gua12345")

# 根据语言环境输出信息
if LOG_LANG == "zh":
    print(f"当前访问密码: {PASSWORD}\n")
else:
    print(f"Current password: {PASSWORD}\n")
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
]

browser_path = os.getenv('CHROME_PATH', "")
if not browser_path:
    print("未设置CHROME_PATH环境变量")
    browser_path = get_browser_path()
    if not browser_path:
        raise ValueError("无法自动定位浏览器路径")

app = FastAPI()


# Pydantic model for the response
class CookieResponse(BaseModel):
    cookies: Dict[str, str]
    user_agent: str


# 密码验证依赖
async def verify_password(password: str):
    if password != PASSWORD:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid password"
        )
    return password


# Function to check if the URL is safe
def is_safe_url(url: str) -> bool:
    parsed_url = urlparse(url)
    ip_pattern = re.compile(
        r"^(127\.0\.0\.1|localhost|0\.0\.0\.0|::1|10\.\d+\.\d+\.\d+|172\.1[6-9]\.\d+\.\d+|172\.2[0-9]\.\d+\.\d+|172\.3[0-1]\.\d+\.\d+|192\.168\.\d+\.\d+)$"
    )
    hostname = parsed_url.hostname
    if (hostname and ip_pattern.match(hostname)) or parsed_url.scheme == "file":
        return False
    return True


def bypass_cloudflare(
    url: str,
    retries: int, 
    log: bool,
    turnstile: bool = False,
    proxy: str = None, 
    user_agent: str = None
) -> ChromiumPage:
    """绕过Cloudflare验证并返回浏览器实例
    
    Args:
        url: 要访问的URL
        retries: 重试次数
        log: 是否启用日志
        proxy: 代理地址
        user_agent: 自定义User-Agent
    
    Returns:
        ChromiumPage: 浏览器实例
        
    Raises:
        Exception: 浏览器操作异常
    """
    options = ChromiumOptions().auto_port()
    
    # 基础配置，所有系统通用
    options.set_argument("-accept-lang=en-US")
    options.add_extension("turnstilePatch")
    options.add_extension("cloudflare_ua_patch")
    options.set_paths(browser_path=browser_path)
    options.headless(os.getenv('HEADLESS', False))
    if user_agent:
        options.set_user_agent(user_agent)
    else:
        options.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    
    # Linux 系统特殊配置
    if platform.system() == "Linux":
        options.set_argument("--auto-open-devtools-for-tabs", "true")
        options.set_argument("--no-sandbox")
        options.set_argument('--disable-dev-shm-usage')
        options.set_argument('--disable-gpu')
        options.set_argument('--disable-software-rasterizer')
        options.set_argument('--lang=en-US')
        options.set_argument('--accept-languages=en-US,en')

    if proxy:
        options.set_proxy(proxy)
        
    driver = ChromiumPage(addr_or_opts=options)
    try:
        driver.get(url)
        cf_bypasser = CloudflareBypasser(driver, retries, log)
        if turnstile:
            cf_bypasser.bypass_turnstile()
        else:
            cf_bypasser.bypass()
        return driver
    except Exception as e:
        driver.quit()
        raise e


# 修改后的cookies端点
@app.get("/{password}/cookies", response_model=CookieResponse)
async def get_cookies(
    password: str = Depends(verify_password),
    url: str = None,
    retries: int = 5,
    proxy: str = None,
    user_agent: str = None
) -> CookieResponse:
    """获取经过Cloudflare验证后的cookies
    
    Args:
        password: 访问密码
        url: 目标URL
        retries: 重试次数(默认5)
        proxy: 代理地址
        user_agent: 自定义User-Agent
    
    Returns:
        CookieResponse: 包含cookies和UA的响应
        
    Raises:
        HTTPException: 请求参数错误或处理失败
    """
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        driver = bypass_cloudflare(url, retries, log, proxy, user_agent)
        retry_interval = 2
        cf_clearance = None
        retry_count = 0
        while retry_count < retries:
            cookies = driver.cookies()
            for cookie in cookies:
                if cookie['name'] == 'cf_clearance':
                    cf_clearance = cookie['value']
                    break

            if cf_clearance:
                break

            retry_count += 1
            time.sleep(retry_interval)
            if LOG_LANG == "zh":
                print(f"正在第{retry_count}次尝试获取cf_clearance...")
            else:
                print(f"Attempt {retry_count}: Trying to get cf_clearance...")

        if not cf_clearance:
            raise ValueError("未能获取到cf_clearance cookie")

        cookies = {cookie.get("name", ""): cookie.get("value", " ") for cookie in driver.cookies()}
        user_agent = driver.user_agent
        driver.quit()
        return CookieResponse(cookies=cookies, user_agent=user_agent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{password}/turnstile", response_model=CookieResponse)
async def get_turnstile_cookies(
        password: str = Depends(verify_password),
        url: str = None,
        retries: int = 5,
        proxy: str = None,
        user_agent: str = None
) -> CookieResponse:
    """获取经过Cloudflare验证后的cookies

    Args:
        password: 访问密码
        url: 目标URL
        retries: 重试次数(默认5)
        proxy: 代理地址
        user_agent: 自定义User-Agent

    Returns:
        CookieResponse: 包含cookies和UA的响应

    Raises:
        HTTPException: 请求参数错误或处理失败
    """
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        driver = bypass_cloudflare(url, retries, log, True, proxy, user_agent)
        retry_interval = 2
        cf_clearance = None
        retry_count = 0
        turnstile_token = ''
        while retry_count < retries:
            cookies = driver.cookies()
            for cookie in cookies:
                if cookie['name'] == 'cf_clearance':
                    cf_clearance = cookie['value']
                    break
            try:
                turnstile = driver.ele('tag:input@name=cf-turnstile-response')
                turnstile_token = turnstile.value
            except Exception as e:
                print(f"获取turnstile_token时出错: {e}")
                pass
            if cf_clearance and turnstile_token:
                break

            retry_count += 1
            time.sleep(retry_interval)
            if LOG_LANG == "zh":
                print(f"正在第{retry_count}次尝试获取cf_clearance和turnstile_token...")
            else:
                print(f"Attempt {retry_count}: Trying to get cf_clearance and turnstile_token...")

        if not cf_clearance:
            raise ValueError("未能获取到cf_clearance cookie和turnstile_token")

        cookies = {cookie.get("name", ""): cookie.get("value", " ") for cookie in driver.cookies()}
        cookies["turnstile_token"] = turnstile_token
        user_agent = driver.user_agent
        driver.quit()
        return CookieResponse(cookies=cookies, user_agent=user_agent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 修改后的html端点
@app.get("/{password}/html")
async def get_html(
    password: str = Depends(verify_password),
    url: str = None,
    retries: int = 5,
    proxy: str = None,
    user_agent: str = None
) -> Response:
    """获取经过Cloudflare验证后的HTML内容
    
    Args:
        password: 访问密码
        url: 目标URL
        retries: 重试次数(默认5)
        proxy: 代理地址
        user_agent: 自定义User-Agent
    
    Returns:
        Response: HTML响应
        
    Raises:
        HTTPException: 请求参数错误或处理失败
    """
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        driver = bypass_cloudflare(url, retries, log, proxy, user_agent)
        html = driver.html
        cookies_json = {cookie.get("name", ""): cookie.get("value", " ") for cookie in driver.cookies()}
        response = Response(content=html, media_type="text/html")
        response.headers["cookies"] = json.dumps(cookies_json)
        response.headers["user_agent"] = driver.user_agent
        driver.quit()
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloudflare bypass api")
    parser.add_argument("--nolog", action="store_true", help="Disable logging")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()
    display = None

    if args.headless:
        display = Display(visible=0, size=(1920, 1080))
        display.start()

        def cleanup_display():
            if display:
                display.stop()

        atexit.register(cleanup_display)

    if args.nolog:
        log = False
    else:
        log = True

    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
