# 相比原项目增加了什么

1. 路径密码，变量名为PASSWORD
2. 增加并优化了arm64的docker镜像，amd64未测试，但是理论上没问题
3. 新增了对ua的限制解除的cloudflare_ua_patch，~~可以开无头了，嘻嘻~~，开不了了，不嘻嘻
4. 新增了对点击检测解除的turnstilePatch
5. 新增获取Turnstile_Token

# Cloudflare Turnstile 页面验证绕过工具

**我们热爱数据采集，不是吗？** 但有时我们会遇到Cloudflare保护。这个脚本旨在绕过网站的Cloudflare保护，让您能够以编程方式与它们交互。

# 这个脚本如何工作？

如果您使用过Selenium，您可能已经注意到无法用它绕过Cloudflare保护。即使您点击了"我不是机器人"按钮，您仍会卡在"正在检查您的浏览器"页面。

这是因为Cloudflare保护能够检测自动化工具并阻止它们，这会使webdriver无限期地停留在"正在检查您的浏览器"页面。

如您所见，本脚本使用DrissionPage，它是浏览器本身的控制器。这样，浏览器不会被检测为webdriver，从而绕过Cloudflare保护。

## 安装

运行以下命令安装所需包：

```bash
pip install -r requirements.txt
```

## 演示
![](https://cdn.sarperavci.com/xWhiMOmD/vzJylR.gif)

## 使用方法

创建`CloudflareBypass`类的新实例，当需要绕过Cloudflare保护时调用`bypass`方法。

```python
from CloudflareBypasser import CloudflareBypasser
from DrissionPage import ChromiumPage

driver = ChromiumPage()
driver.get('https://nopecha.com/demo/cloudflare')

cf_bypasser = CloudflareBypasser(driver)
cf_bypasser.bypass()
```

您可以运行测试脚本查看效果：

```bash
python test.py
```

# 服务器模式介绍

最近，[@frederik-uni](https://github.com/frederik-uni) 引入了"服务器模式"新功能。此功能允许您远程绕过Cloudflare保护，您可以获取网站的cookies或HTML内容。

## 安装

运行以下命令安装所需包：

```bash
pip install -r server_requirements.txt
```

## 使用方法

运行以下命令启动服务器：

```bash
python server.py
```

提供三个端点：
- `/turnstile?url=<URL>&user_agent=<UA>&retries=<>&proxy=<>`: 返回网站的cookies(包括Cloudflare cookies和 Turnstile_token)
- `/cookies?url=<URL>&user_agent=<UA>&retries=<>&proxy=<>`: 返回网站的cookies(包括Cloudflare cookies)
- `/html?url=<URL>user_agent=<UA>&retries=<>&proxy=<>`: 返回网站的HTML内容

向所需端点发送GET请求，附带您想要绕过Cloudflare保护的网站URL。

```bash
sarp@IdeaPad:~/$ curl "http://127.0.0.1:8000/gua12345/cookies?url=https://nopecha.com/demo/cloudflare&user_agent=Mozilla/5.0%20(Windows%20NT%2010.0;%20Win64;%20x64)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/129.0.0.0%20Safari/537.36"
{"cookies":{"cf_clearance":"WVwnPg15ZmHeQuSp0LgmsLfdMd4WUFmMY9g7A.xFiYE-1743576949-1.2.1.1-oPLWfZFXYsDNn1m34U2WNuH3lCkGuTGtnSUEcM1BPZX.Dw1EGecnpA2zoZaO3sNObNec6g9zmqIq5vVmGYrtu_INf_Vs5V__.p74XLOeYie0Qr5RPkeoI.uFnrPlLMqKNgPa1dQOhIKRFIm6Zpb4.QIeb_y1FiesqfzANN_PWPOLzugWmEpe._lei_n9jRDw5HrBvLQ4H93D9i8pJB81pALBtKGPHY7u_H8Cqg72UpAUBOH5ucYOjEdtcHl0waNDLZeE4sh.VUkvhwX8gulXZspWlKJVkmLuHKRZKKFMuidRy1gh4osIPih7qzBK8OxiXjT2lsQzxFYVWjx1sVbje3LTEYeYoPg7GeINO6HYRCr_QhO5DCqvtag3E09gbYGw1diXyK2Z3ihaw847Lgd5HwzBepifrRHsaCuIw5QfkPU"},"user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"}
```

## Docker

您也可以在Docker容器中运行服务器。感谢 @gandrunx 提供初版的容器构建方案。我自己更改后重新打包了Docker，但是镜像大小还是太大，介意的请尝试优化

首先构建Docker镜像：

```bash
docker build -t cloudflare-bypass .
```

然后运行Docker容器：

```bash
docker run -p 8000:8000 cloudflare-bypass
```

或者，您可以跳过`docker build`步骤，直接使用预构建的镜像运行容器：

```bash
docker run -p 8000:8000 gua12345/cloudflarebypassforscraping:latest
```

## 示例项目

以下是一些使用CloudflareBypasser服务器的示例项目：

- [Calibre Web自动书籍下载器](https://github.com/calibrain/calibre-web-automated-book-downloader) - 从calibre web下载书籍的工具
- [Kick非官方API](https://github.com/sarperavci/kick-unofficial-api) - 与Kick.com交互的工具，可下载视频、发送消息等

## 致谢

本项目基于 [sarperavci](https://github.com/sarperavci) 的原创项目进行二次开发。感谢原作者的开源贡献。

<div align="center">
  <img src="https://avatars.githubusercontent.com/u/50243344?v=4" alt="sarperavci" width="100" style="border-radius: 50%"/>
</div>
