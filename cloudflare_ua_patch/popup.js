document.addEventListener('DOMContentLoaded', function() {
  // 获取当前UA并显示
  const uaSpan = document.getElementById('current-ua');
  const statusSpan = document.getElementById('status');
  const toggleButton = document.getElementById('toggle');
  const refreshButton = document.getElementById('refresh');

  // 首先尝试ping background service worker以确保它是活跃的
  chrome.runtime.sendMessage({action: "ping"}, function(response) {
    if (response && response.status === "pong") {
      console.log("Background service worker 已激活");
      loadStatus();
    } else {
      console.log("Background service worker 未响应，尝试激活它");
      // 尝试通过获取状态来激活background
      chrome.runtime.sendMessage({action: "getStatus"}, function(response) {
        if (response) {
          console.log("成功激活 background service worker");
          loadStatus();
        } else {
          console.log("无法激活 background service worker，从存储加载状态");
          loadStatusFromStorage();
        }
      });
    }
  });

  function loadStatus() {
    chrome.runtime.sendMessage({action: "getStatus"}, function(response) {
      if (response) {
        updateUI(response.enabled);
      } else {
        loadStatusFromStorage();
      }
    });

    // 显示当前UA
    uaSpan.textContent = navigator.userAgent;
    console.log("当前UA:", navigator.userAgent);
  }

  function loadStatusFromStorage() {
    chrome.storage.local.get(['enabled', 'userAgent', 'clientHintsConfig'], function(result) {
      const enabled = result.enabled === undefined ? true : result.enabled;
      updateUI(enabled);
      if (result.userAgent) {
        uaSpan.textContent = result.userAgent;
      } else {
        uaSpan.textContent = navigator.userAgent;
      }
    });
  }

  // 切换启用/禁用状态
  toggleButton.addEventListener('click', function() {
    chrome.storage.local.get(['enabled'], function(result) {
      const currentlyEnabled = result.enabled === undefined ? true : result.enabled;
      const newEnabled = !currentlyEnabled;
      console.log("切换状态:", currentlyEnabled, "->", newEnabled);

      if (newEnabled) {
        // 重新启用规则
        chrome.storage.local.get(['clientHintsConfig'], function(result) {
          if (result.clientHintsConfig) {
            console.log("重新启用规则，使用配置:", result.clientHintsConfig);
            chrome.runtime.sendMessage({
              action: "updateRules",
              config: result.clientHintsConfig
            }, function(response) {
              console.log("启用规则响应:", response);
              chrome.storage.local.set({enabled: newEnabled}, function() {
                updateUI(newEnabled);
              });
            });
          } else {
            console.log("没有找到存储的配置，使用当前UA");
            const newUA = navigator.userAgent;
            const clientHintsConfig = parseUserAgent(newUA);
            chrome.runtime.sendMessage({
              action: "updateRules",
              config: clientHintsConfig
            }, function(response) {
              console.log("启用规则响应:", response);
              chrome.storage.local.set({
                enabled: newEnabled,
                userAgent: newUA,
                clientHintsConfig: clientHintsConfig
              }, function() {
                updateUI(newEnabled);
              });
            });
          }
        });
      } else {
        // 禁用规则
        console.log("禁用规则");
        chrome.runtime.sendMessage({
          action: "updateRules",
          config: {
            brand: '',
            platform: 'Windows',
            mobile: '?0',
            arch: 'x86',
            bitness: '64',
            fullVersion: '',
            model: '',
            platformVersion: '10.0.0'
          }
        }, function(response) {
          console.log("禁用规则响应:", response);
          chrome.storage.local.set({enabled: newEnabled}, function() {
            updateUI(newEnabled);
          });
        });
      }
    });
  });

  // 刷新UA信息
  refreshButton.addEventListener('click', function() {
    const newUA = navigator.userAgent;
    uaSpan.textContent = newUA;
    console.log("刷新UA:", newUA);

    // 解析新UA并更新规则
    const clientHintsConfig = parseUserAgent(newUA);
    console.log("新解析的配置:", clientHintsConfig);

    // 显示加载状态
    statusSpan.textContent = '正在更新...';
    chrome.runtime.sendMessage({
      action: "updateRules",
      config: clientHintsConfig
    }, function(response) {
      console.log("更新规则响应:", response);
      if (response && response.success) {
        statusSpan.textContent = '已启用';
        // 存储新配置
        chrome.storage.local.set({
          enabled: true,
          userAgent: newUA,
          clientHintsConfig: clientHintsConfig
        });
      } else {
        statusSpan.textContent = '更新失败';
        console.error("更新失败原因:", response ? response.error : "未知错误");
      }
    });
  });

  function updateUI(enabled) {
    if (enabled) {
      statusSpan.textContent = '已启用';
      toggleButton.textContent = '禁用';
    } else {
      statusSpan.textContent = '已禁用';
      toggleButton.textContent = '启用';
    }
  }

  // 解析UA函数 (与background.js中相同)
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

    // Chrome
    if (ua.includes('Chrome')) {
      const chromeMatch = ua.match(/Chrome\/(\d+\.\d+\.\d+\.\d+)/);
      if (chromeMatch) {
        result.fullVersion = chromeMatch[1];
        result.brand = `"Chromium";v="${chromeMatch[1].split('.')[0]}", "Google Chrome";v="${chromeMatch[1].split('.')[0]}", "Not;A=Brand";v="99"`;
      }
    }
    // Firefox
    else if (ua.includes('Firefox')) {
      const firefoxMatch = ua.match(/Firefox\/(\d+\.\d+)/);
      if (firefoxMatch) {
        result.fullVersion = firefoxMatch[1];
        result.brand = `"Firefox";v="${firefoxMatch[1].split('.')[0]}", "Not;A=Brand";v="99"`;
      }
    }

    // 操作系统检测
    if (ua.includes('Windows')) {
      result.platform = 'Windows';
      const winMatch = ua.match(/Windows NT (\d+\.\d+)/);
      if (winMatch) {
        result.platformVersion = winMatch[1] + '.0';
      }
    } else if (ua.includes('Macintosh')) {
      result.platform = 'macOS';
      const macMatch = ua.match(/Mac OS X (\d+[._]\d+[._]\d+)/);
      if (macMatch) {
        result.platformVersion = macMatch[1].replace(/_/g, '.');
      }
    } else if (ua.includes('Linux')) {
      result.platform = 'Linux';
      result.platformVersion = '';
    } else if (ua.includes('Android')) {
      result.platform = 'Android';
      result.mobile = '?1';
      const androidMatch = ua.match(/Android (\d+\.\d+)/);
      if (androidMatch) {
        result.platformVersion = androidMatch[1];
      }

      // 尝试提取设备型号
      const modelMatch = ua.match(/;\s([^;]+)\sBuild\//);
      if (modelMatch) {
        result.model = modelMatch[1];
      }
    } else if (ua.includes('iPhone') || ua.includes('iPad')) {
      result.platform = ua.includes('iPhone') ? 'iPhone' : 'iPad';
      result.mobile = ua.includes('iPhone') ? '?1' : '?0';
      const iosMatch = ua.match(/OS (\d+_\d+)/);
      if (iosMatch) {
        result.platformVersion = iosMatch[1].replace('_', '.');
      }
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

    return result;
  }
});