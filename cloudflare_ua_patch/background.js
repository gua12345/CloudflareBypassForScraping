// 初始化扩展
chrome.runtime.onInstalled.addListener(async () => {
  // 获取当前UA并生成规则
  const userAgent = navigator.userAgent;
  console.log("当前UA:", userAgent);
  const clientHintsConfig = parseUserAgent(userAgent);
  console.log("解析后的配置:", clientHintsConfig);
  // 创建并应用动态规则
  await updateDynamicRules(clientHintsConfig);
  // 存储配置
  chrome.storage.local.set({
    enabled: true,
    userAgent: userAgent,
    clientHintsConfig: clientHintsConfig
  });
});

// 添加更多事件监听器以提高启动成功率
chrome.runtime.onStartup.addListener(async () => {
  console.log("浏览器启动，扩展被激活");
  await initializeExtension();
});

// 监听标签页更新事件，确保扩展保持活跃
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.active) {
    console.log("标签页更新完成，检查扩展状态");
    checkAndInitializeIfNeeded();
  }
});

// 监听标签页激活事件
chrome.tabs.onActivated.addListener(() => {
  console.log("标签页被激活，检查扩展状态");
  checkAndInitializeIfNeeded();
});

// 检查并在需要时初始化扩展
async function checkAndInitializeIfNeeded() {
  try {
    // 检查是否有活跃规则
    const rules = await chrome.declarativeNetRequest.getDynamicRules();
    if (rules.length === 0) {
      console.log("未检测到活跃规则，重新初始化扩展");
      await initializeExtension();
    } else {
      console.log("检测到活跃规则，扩展正常运行中");
    }
  } catch (error) {
    console.error("检查规则状态时出错:", error);
    await initializeExtension();
  }
}

// 初始化扩展函数
async function initializeExtension() {
  try {
    const data = await chrome.storage.local.get(['enabled', 'clientHintsConfig']);
    if (data.enabled) {
      console.log("从存储中恢复配置:", data.clientHintsConfig);
      await updateDynamicRules(data.clientHintsConfig);
    } else {
      console.log("扩展被禁用，不应用规则");
    }
  } catch (error) {
    console.error("初始化扩展时出错:", error);
    // 出错时使用当前UA重新生成配置
    const userAgent = navigator.userAgent;
    const clientHintsConfig = parseUserAgent(userAgent);
    await updateDynamicRules(clientHintsConfig);
    chrome.storage.local.set({
      enabled: true,
      userAgent: userAgent,
      clientHintsConfig: clientHintsConfig
    });
  }
}

// 监听消息，用于从popup更新规则
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "updateRules") {
    console.log("收到更新规则请求:", message.config);
    // 更新动态规则
    updateDynamicRules(message.config)
      .then(() => {
        console.log("动态规则更新成功");
        sendResponse({ success: true });
      })
      .catch(error => {
        console.error("动态规则更新失败:", error);
        sendResponse({ success: false, error: error.message });
      });
    return true; // 表示将异步发送响应
  } else if (message.action === "getStatus") {
    // 添加获取状态的处理
    chrome.storage.local.get(['enabled', 'clientHintsConfig'], (data) => {
      sendResponse({
        enabled: data.enabled === undefined ? true : data.enabled,
        config: data.clientHintsConfig
      });
    });
    return true;
  } else if (message.action === "ping") {
    // 简单的ping-pong机制，用于检测service worker是否活跃
    console.log("收到ping请求");
    sendResponse({ status: "pong" });
    return true;
  }
});

// 更新动态规则
async function updateDynamicRules(config) {
  try {
    console.log("开始更新动态规则，配置:", config);
    // 1. 获取所有当前动态规则
    const currentRules = await chrome.declarativeNetRequest.getDynamicRules();
    console.log("当前动态规则:", currentRules);
    // 2. 删除所有现有动态规则
    const ruleIdsToRemove = currentRules.map(rule => rule.id);
    // 3. 创建新动态规则
    const newRules = [
      {
        "id": 1,
        "priority": 1,
        "action": {
          "type": "modifyHeaders",
          "requestHeaders": [
            { "header": "sec-ch-ua", "operation": "set", "value": config.brand },
            { "header": "sec-ch-ua-platform", "operation": "set", "value": `"${config.platform}"` },
            { "header": "sec-ch-ua-mobile", "operation": "set", "value": config.mobile },
            { "header": "sec-ch-ua-arch", "operation": "set", "value": `"${config.arch}"` },
            { "header": "sec-ch-ua-bitness", "operation": "set", "value": `"${config.bitness}"` },
            { "header": "sec-ch-ua-full-version", "operation": "set", "value": `"${config.fullVersion}"` },
            { "header": "sec-ch-ua-model", "operation": "set", "value": config.model ? `"${config.model}"` : '""' },
            { "header": "sec-ch-ua-platform-version", "operation": "set", "value": `"${config.platformVersion}"` }
          ]
        },
        "condition": {
          "urlFilter": "*",
          "resourceTypes": ["main_frame", "sub_frame", "stylesheet", "script", "image", "font", "object", "xmlhttprequest", "ping", "csp_report", "media", "websocket", "other"]
        }
      }
    ];
    // 4. 在一个操作中删除所有旧规则并添加新规则
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: ruleIdsToRemove,
      addRules: newRules
    });
    // 5. 验证规则是否已更新
    const updatedRules = await chrome.declarativeNetRequest.getDynamicRules();
    console.log("更新后的动态规则:", updatedRules);
    if (updatedRules.length !== newRules.length) {
      throw new Error(`规则数量不匹配: 预期 ${newRules.length}, 实际 ${updatedRules.length}`);
    }
    console.log("动态规则已成功更新");

    // 6. 刷新所有标签页
    try {
      const tabs = await chrome.tabs.query({});
      console.log(`准备刷新 ${tabs.length} 个标签页`);

      for (const tab of tabs) {
        // 跳过扩展页面和特殊页面
        if (!tab.url.startsWith('chrome://') &&
            !tab.url.startsWith('chrome-extension://') &&
            !tab.url.startsWith('edge://') &&
            !tab.url.startsWith('about:')) {
          console.log(`刷新标签页: ${tab.id} - ${tab.url}`);
          await chrome.tabs.reload(tab.id);
        } else {
          console.log(`跳过特殊标签页: ${tab.id} - ${tab.url}`);
        }
      }
      console.log("所有标签页刷新完成");
    } catch (refreshError) {
      console.error("刷新标签页时出错:", refreshError);
      // 刷新失败不影响规则更新的结果
    }

    return true;
  } catch (error) {
    console.error("更新动态规则失败:", error);
    throw error;
  }
}

// 解析UA函数
function parseUserAgent(ua) {
  let result = {
    brand: '',
    platform: 'Windows',
    mobile: '?0',
    arch: 'x86',
    bitness: '64',
    fullVersion: '',
    model: '',
    platformVersion: '10.0.0'
  };
  console.log('开始解析UA：', ua);

  // Chrome
  if (ua.includes('Chrome')) {
    const chromeMatch = ua.match(/Chrome\/(\d+\.\d+\.\d+\.\d+)/);
    if (chromeMatch) {
      result.fullVersion = chromeMatch[1];
      result.brand = `"Chromium";v="${chromeMatch[1].split('.')[0]}", "Not;A=Brand";v="99", "Google Chrome";v="${chromeMatch[1].split('.')[0]}"`;
      console.log('Chrome检测结果：', { fullVersion: result.fullVersion, brand: result.brand });
    }
  }
  // Firefox
  else if (ua.includes('Firefox')) {
    const firefoxMatch = ua.match(/Firefox\/(\d+\.\d+)/);
    if (firefoxMatch) {
      result.fullVersion = firefoxMatch[1];
      result.brand = `"Firefox";v="${firefoxMatch[1].split('.')[0]}", "Not;A=Brand";v="99"`;
      console.log('Firefox检测结果：', { fullVersion: result.fullVersion, brand: result.brand });
    }
  }

  // 操作系统检测
  if (ua.includes('Windows')) {
    result.platform = 'Windows';
    const winMatch = ua.match(/Windows NT (\d+\.\d+)/);
    if (winMatch) {
      result.platformVersion = winMatch[1] + '.0';
    }
    console.log('Windows检测：', { platform: result.platform, platformVersion: result.platformVersion });
  } else if (ua.includes('Macintosh')) {
    result.platform = 'macOS';
    const macMatch = ua.match(/Mac OS X (\d+[._]\d+[._]\d+)/);
    if (macMatch) {
      result.platformVersion = macMatch[1].replace(/_/g, '.');
    }
    console.log('macOS检测：', { platform: result.platform, platformVersion: result.platformVersion });
  } else if (ua.includes('Linux')) {
    result.platform = 'Linux';
    result.platformVersion = '';
    console.log('Linux检测：', { platform: result.platform });
  } else if (ua.includes('Android')) {
    result.platform = 'Android';
    result.mobile = '?1';
    const androidMatch = ua.match(/Android (\d+\.\d+)/);
    if (androidMatch) {
      result.platformVersion = androidMatch[1];
    }
    const modelMatch = ua.match(/;\s([^;]+)\sBuild\//);
    if (modelMatch) {
      result.model = modelMatch[1];
    }
    console.log('Android检测：', { platform: result.platform, platformVersion: result.platformVersion, model: result.model });
  } else if (ua.includes('iPhone') || ua.includes('iPad')) {
    result.platform = ua.includes('iPhone') ? 'iPhone' : 'iPad';
    result.mobile = ua.includes('iPhone') ? '?1' : '?0';
    const iosMatch = ua.match(/OS (\d+_\d+)/);
    if (iosMatch) {
      result.platformVersion = iosMatch[1].replace('_', '.');
    }
    console.log('iOS检测：', { platform: result.platform, mobile: result.mobile, platformVersion: result.platformVersion });
  }

  // 架构检测 (简化版)
  if (ua.includes('x64') || ua.includes('x86_64') || ua.includes('Win64')) {
    result.arch = 'x86';
    result.bitness = '64';
  } else if (ua.includes('x86') || ua.includes('i686')) {
    result.arch = 'x86';
    result.bitness = '32';
  } else if (ua.includes('arm')) {
    result.arch = 'arm';
    if (ua.includes('arm64')) {
      result.bitness = '64';
    } else {
      result.bitness = '32';
    }
  }
  console.log('架构检测：', { arch: result.arch, bitness: result.bitness });
  console.log('解析完成，返回结果：', result);
  return result;
}