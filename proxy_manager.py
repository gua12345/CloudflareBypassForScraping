import subprocess
import random
import time
import psutil
from CloudflareBypasser import logging, LOG_LANG
import re
import socket

# 存储代理进程的字典，键为端口号，值为进程对象
_proxy_processes = {}


def start_proxy_with_auth(auth_proxy: str) -> str:
    """
    将带认证的代理转换为随机端口的无验证本地代理。
    Args:
        auth_proxy (str): 带认证的代理地址，例如 "http://username:password@proxy_host:proxy_port"
    Returns:
        str: 返回本地代理地址带http协议
    Raises:
        RuntimeError: 如果 mitmdump 启动失败
    """
    log_prefix = "代理服务" if LOG_LANG == "zh" else "Proxy Service"
    logging.info(
        f"{log_prefix}: 开始启动带认证的代理服务" if LOG_LANG == "zh" else f"{log_prefix}: Starting authenticated proxy service")

    # 解析代理地址
    match = re.match(r"(http://)?([^:]+):([^@]+)@([^:]+):(\d+)", auth_proxy)
    if not match:
        error_msg = f"无效的代理格式: {auth_proxy}" if LOG_LANG == "zh" else f"Invalid proxy format: {auth_proxy}"
        logging.error(f"{log_prefix}: {error_msg}")
        raise ValueError(error_msg)

    _, username, password, host, port = match.groups()
    # 隐藏密码的日志记录
    masked_auth = f"{username}:****"
    logging.info(f"{log_prefix}: 解析代理地址成功，上游代理: {host}:{port}" if LOG_LANG == "zh" else
                 f"{log_prefix}: Successfully parsed proxy address, upstream: {host}:{port}")

    upstream_server = f"http://{host}:{port}"
    auth = f"{username}:{password}"

    # 生成随机端口（避免冲突）
    local_port = None
    attempts = 0
    max_port_attempts = 10

    while attempts < max_port_attempts:
        temp_port = random.randint(1024, 65535)
        if temp_port not in _proxy_processes and not _is_port_in_use(temp_port):
            local_port = temp_port
            break
        attempts += 1
        logging.debug(
            f"{log_prefix}: 端口 {temp_port} 已被占用，尝试其他端口 ({attempts}/{max_port_attempts})" if LOG_LANG == "zh" else
            f"{log_prefix}: Port {temp_port} is in use, trying another port ({attempts}/{max_port_attempts})")

    if local_port is None:
        error_msg = "无法找到可用端口" if LOG_LANG == "zh" else "Could not find available port"
        logging.error(f"{log_prefix}: {error_msg}")
        raise RuntimeError(error_msg)

    logging.info(f"{log_prefix}: 选择本地端口 {local_port}" if LOG_LANG == "zh" else
                 f"{log_prefix}: Selected local port {local_port}")

    # 构造 mitmdump 命令
    cmd = [
        "mitmdump",
        "--mode", f"upstream:{upstream_server}",
        "--upstream-auth", auth,
        "--listen-host", "127.0.0.1",  # 只绑定到 localhost
        "--listen-port", str(local_port),
        "--quiet",  # 静默模式，避免过多日志输出
        "--set", "block_global=false",  # 允许外部连接
        "--ssl-insecure",  # 忽略证书错误
    ]

    # 记录命令（隐藏敏感信息）
    log_cmd = cmd.copy()
    auth_index = log_cmd.index("--upstream-auth") + 1
    log_cmd[auth_index] = masked_auth
    logging.debug(f"{log_prefix}: 执行命令: {' '.join(log_cmd)}" if LOG_LANG == "zh" else
                  f"{log_prefix}: Executing command: {' '.join(log_cmd)}")

    # 启动 mitmdump 进程
    try:
        logging.info(f"{log_prefix}: 正在启动 mitmdump 进程..." if LOG_LANG == "zh" else
                     f"{log_prefix}: Starting mitmdump process...")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 等待代理启动并验证可用性
        logging.info(f"{log_prefix}: 等待代理服务就绪..." if LOG_LANG == "zh" else
                     f"{log_prefix}: Waiting for proxy service to be ready...")
        if not _wait_for_proxy_ready(local_port, max_attempts=10):
            # 如果代理未能成功启动，终止进程并抛出异常
            process.terminate()
            error = process.stderr.read().decode()
            error_msg = f"代理在端口 {local_port} 上启动失败: {error}" if LOG_LANG == "zh" else f"Proxy failed to start on port {local_port}: {error}"
            logging.error(f"{log_prefix}: {error_msg}")
            raise RuntimeError(error_msg)

        # 检查进程是否仍在运行
        if process.poll() is not None:
            error = process.stderr.read().decode()
            error_msg = f"启动 mitmdump 失败: {error}" if LOG_LANG == "zh" else f"Failed to start mitmdump: {error}"
            logging.error(f"{log_prefix}: {error_msg}")
            raise RuntimeError(error_msg)

        # 存储进程
        _proxy_processes[local_port] = process
        proxy_address = f"http://127.0.0.1:{local_port}"  # 返回带 http:// 的代理地址
        logging.info(f"{log_prefix}: 代理服务成功启动，本地地址: {proxy_address}" if LOG_LANG == "zh" else
                     f"{log_prefix}: Proxy service successfully started, local address: {proxy_address}")
        return proxy_address
    except Exception as e:
        error_msg = f"启动代理时出错: {str(e)}" if LOG_LANG == "zh" else f"Error starting proxy: {str(e)}"
        logging.error(f"{log_prefix}: {error_msg}")
        raise RuntimeError(error_msg)


def _wait_for_proxy_ready(port: int, max_attempts: int = 10, delay: float = 0.5) -> bool:
    """
    等待代理服务器准备就绪，通过尝试连接到指定端口来验证。
    Args:
        port: 代理服务器的端口
        max_attempts: 最大尝试次数
        delay: 每次尝试之间的延迟（秒）
    Returns:
        bool: 如果代理服务器准备就绪返回 True，否则返回 False
    """
    log_prefix = "代理服务" if LOG_LANG == "zh" else "Proxy Service"
    for attempt in range(max_attempts):
        try:
            # 尝试建立到代理端口的TCP连接
            logging.debug(
                f"{log_prefix}: 尝试连接到端口 {port} (尝试 {attempt + 1}/{max_attempts})" if LOG_LANG == "zh" else
                f"{log_prefix}: Attempting to connect to port {port} (attempt {attempt + 1}/{max_attempts})")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(('127.0.0.1', port))
                logging.info(f"{log_prefix}: 成功连接到端口 {port}，代理服务已就绪" if LOG_LANG == "zh" else
                             f"{log_prefix}: Successfully connected to port {port}, proxy service is ready")
                return True  # 连接成功，代理已准备就绪
        except (socket.timeout, ConnectionRefusedError) as e:
            # 连接失败，等待后重试
            logging.debug(f"{log_prefix}: 连接到端口 {port} 失败: {str(e)}，{delay}秒后重试" if LOG_LANG == "zh" else
                          f"{log_prefix}: Failed to connect to port {port}: {str(e)}, retrying in {delay} seconds")
            time.sleep(delay)

    logging.error(f"{log_prefix}: 达到最大尝试次数后仍无法连接到端口 {port}" if LOG_LANG == "zh" else
                  f"{log_prefix}: Could not connect to port {port} after maximum attempts")
    return False  # 达到最大尝试次数后仍未成功


def stop_proxy(proxy_address: str) -> bool:
    """
    关闭指定的无验证代理，释放端口和资源。
    Args:
        proxy_address (str): 本地代理地址，带协议，例如 "http://127.0.0.1:端口"
    Returns:
        bool: 成功关闭返回 True，否则返回 False
    """
    log_prefix = "代理服务" if LOG_LANG == "zh" else "Proxy Service"
    logging.info(f"{log_prefix}: 尝试关闭代理 {proxy_address}" if LOG_LANG == "zh" else
                 f"{log_prefix}: Attempting to stop proxy {proxy_address}")

    # 从代理地址中提取端口号
    try:
        # 移除 "http://" 前缀并提取端口
        port_str = proxy_address.replace("http://", "").split(":")[-1]
        port = int(port_str)
        logging.debug(f"{log_prefix}: 从地址 {proxy_address} 提取端口 {port}" if LOG_LANG == "zh" else
                      f"{log_prefix}: Extracted port {port} from address {proxy_address}")
    except (ValueError, IndexError) as e:
        error_msg = f"无效的代理地址格式: {proxy_address}, 错误: {str(e)}" if LOG_LANG == "zh" else f"Invalid proxy address format: {proxy_address}, error: {str(e)}"
        logging.error(f"{log_prefix}: {error_msg}")
        print(error_msg)
        return False

    if port not in _proxy_processes:
        logging.warning(f"{log_prefix}: 端口 {port} 没有关联的代理进程" if LOG_LANG == "zh" else
                        f"{log_prefix}: No proxy process associated with port {port}")
        return False

    process = _proxy_processes[port]
    try:
        # 终止进程及其子进程
        logging.info(f"{log_prefix}: 正在终止端口 {port} 上的代理进程 (PID: {process.pid})" if LOG_LANG == "zh" else
                     f"{log_prefix}: Terminating proxy process on port {port} (PID: {process.pid})")

        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        if children:
            logging.debug(f"{log_prefix}: 发现 {len(children)} 个子进程，正在终止" if LOG_LANG == "zh" else
                          f"{log_prefix}: Found {len(children)} child processes, terminating")
            for child in children:
                child.terminate()
                logging.debug(f"{log_prefix}: 已终止子进程 PID: {child.pid}" if LOG_LANG == "zh" else
                              f"{log_prefix}: Terminated child process PID: {child.pid}")

        parent.terminate()
        logging.debug(f"{log_prefix}: 已终止父进程 PID: {parent.pid}" if LOG_LANG == "zh" else
                      f"{log_prefix}: Terminated parent process PID: {parent.pid}")

        # 等待进程结束
        logging.debug(f"{log_prefix}: 等待进程完全退出..." if LOG_LANG == "zh" else
                      f"{log_prefix}: Waiting for process to fully exit...")
        process.wait(timeout=5)

        # 清理字典
        del _proxy_processes[port]
        logging.info(f"{log_prefix}: 成功关闭端口 {port} 上的代理" if LOG_LANG == "zh" else
                     f"{log_prefix}: Successfully stopped proxy on port {port}")
        return True
    except Exception as e:
        error_msg = f"关闭代理 {proxy_address} 时出错: {str(e)}" if LOG_LANG == "zh" else f"Error stopping proxy at {proxy_address}: {str(e)}"
        logging.error(f"{log_prefix}: {error_msg}")
        print(error_msg)
        return False


def _is_port_in_use(port: int) -> bool:
    """
    检查端口是否已被占用。
    """
    log_prefix = "代理服务" if LOG_LANG == "zh" else "Proxy Service"
    try:
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                logging.debug(f"{log_prefix}: 端口 {port} 已被占用" if LOG_LANG == "zh" else
                              f"{log_prefix}: Port {port} is in use")
                return True
        logging.debug(f"{log_prefix}: 端口 {port} 可用" if LOG_LANG == "zh" else
                      f"{log_prefix}: Port {port} is available")
        return False
    except Exception as e:
        logging.warning(f"{log_prefix}: 检查端口 {port} 是否被占用时出错: {str(e)}" if LOG_LANG == "zh" else
                        f"{log_prefix}: Error checking if port {port} is in use: {str(e)}")
        # 如果出错，保守地假设端口已被占用
        return True