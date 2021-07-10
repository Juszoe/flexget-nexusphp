# flexget-nexusphp
Flexget插件，增强对NexusPHP的过滤<br>
过滤条件包括种子优惠信息（free等）、做种者情况、下载者情况
- [站点支持列表](#site)
- [支持作者](#donate) **插件维护离不开大家的支持**
---
更多插件：[IO过高时停止任务插件](https://github.com/Juszoe/flexget-limiter)

## 免责声明
本插件会爬取details.php页面，请将参数限制到合理的范围，减轻对服务器负担<br>
本插件已尽量减轻服务器负担，因本插件造成账号封禁等损失，请自行承担后果<br>
**建议** 将RSS条目限制在20条以内，将Flexget运行频率设置在10分钟以上。
如果不想对人数进行过滤，不建议设置seeders和leechers参数。<br>

## 运行环境
- [Flexget](https://flexget.com/)
- Python 3.X 或 Python 2.7 [其他版本解决方案](#version)

## 安装插件
1. 下载插件 [nexusphp.py](https://github.com/Juszoe/flexget-nexusphp/releases)
2. 在Flexget配置文件夹下新建plugins文件夹，例如：
```
~/.flexget/plugins/  # Linux
C:\Users\<YOURUSER>\flexget\plugins\  # Windows
```
再次注意`plugins`文件夹和`config.yml`处在同一级目录下，例如：
```
/.flxget
  ┕━config.yml
  ┕━plugins
    ┕━nexusphp.py
```
3. 将插件拷贝至plugins
4. 若启用了Web-UI或守护进程，则重启flexget重新加载配置

## 使用
1. 编辑flexget配置文件，添加nexusphp选项，按照需要进行配置
#### 简单配置
```yaml
nexusphp:
  cookie: 'a=xxx; b=xxx'  # 必填
  discount:  # 优惠信息 选填
    - free
```
#### 完整配置
```yaml
nexusphp:
  cookie: 'a=xxx; b=xxx'  # 必填
  discount:  # 优惠信息 选填
    - free
    - 2x
    - 2x50%
    - 2xfree
    - 50%
    - 30%
  seeders:  # 做种情况 选填
    min: 1
    max: 2
  leechers:  # 下载情况 选填
    min: 10
    max: 100
    max_complete: 0.8
  left-time: 1 hours  # 优惠剩余时间 选填
  hr: no  # 是否下载HR 选填
  adapter:  # 站点适配器，自行适配站点，参考最下方常见问题 选填
    free: free
    2x: twoup
    2xfree: twoupfree
    30%: thirtypercent
    50%: halfdown
    2x50%: twouphalfdown
  comment: no  # 在torrent注释中添加详情链接 选填
  user-agent: xxxxxx  # 浏览器标识 选填
  remember: yes  # 记住优惠信息 选填 请勿随意设置
```
2. 为rss的other_fields字段添加link属性
```yaml
rss: 
  url: https://www.example.com/rss
  other_fields: [link]
```
3. 启动flexget
``` bash
flexget execute
# 如果仅仅想要测试而不下载，可以添加 --test 参数
flexget --test execute
```

## 详细配置
- `cookie` **网站cookie** 必须填写
- `discount` **优惠类型** 默认不限制优惠类型。<br>
列表类型，Flexget会只下载含有列表内优惠类型的种子。<br>
有效值：`free 2x 2x50% 2xfree 50% 30%`<br>
`注意：x为英文字母`
- `seeders` **做种情况** 做种人数超出范围的，Flexget将不会下载
  - `min` 最小做种人数。整数，默认不限制
  - `max` 最大做种人数。整数，默认不限制
- `leechers` **下载情况** 下载人数超出范围的，Flexget将不会下载
  - `min` 最小下载人数。整数，默认不限制
  - `max` 最大下载人数。整数，默认不限制
- `max_complete` **下载者中最大完成度** 超过这个值将不下载。
小数，范围`0-1.0`，默认为1
- `left-time` **最小剩余时间** 当实际剩余时间小于设置的值，则不下载。
时间字符串，例如 `3 hours`、`10 minutes`、`1 days`。
例如设置`1 hours`，优惠剩余59分钟，那么就不下载。默认不限制
- `hr` **是否下载HR种** 默认 yes<br>
  1. `yes` 会下载HR，即不过滤HR<br>
  2. `no` 不下载HR<br>
- `adapter` **站点适配器** 站点不兼容时可自定义，具体参考
[判断站点以及适配站点](https://github.com/Juszoe/flexget-nexusphp/blob/master/site.md)
- `comment` **在torrent注释中添加详情链接**<br>
  1. `yes` 在torrent注释中添加详情链接，方便在BT客户端查看<br>
  2. `no` 默认值<br>
- `user-agent` **浏览器标识** 默认为Google浏览器
- `remember` **记住优惠信息** 不建议设置为 no，因为会增大站点压力。默认 yes


## 完整配置示例
### 免费热种
```yaml
tasks:
  my-free-task:
    rss: 
      url: https://www.example.com/rss.xml
      other_fields:
        - link
    nexusphp:
      cookie: 'a=xxx; b=xxx'
      discount:
        - free
        - 2xfree
      seeders:
        min: 1
        max: 3
      leechers:
        min: 5
        max_complete: 0.5
    download: ~/flexget/torrents/
```
### 热种
```yaml
tasks:
  my-hot-task:
    rss: 
      url: https://www.example.com/rss.xml
      other_fields:
        - link
    nexusphp:
      cookie: 'a=xxx; b=xxx'
      seeders:
        min: 1
      leechers:
        min: 20
    download: ~/flexget/torrents/
```
### 避免HR
```yaml
tasks:
  no-hr-task:
    rss: 
      url: https://www.example.com/rss.xml
      other_fields:
        - link
    nexusphp:
      cookie: 'a=xxx; b=xxx'
      hr: no
    download: ~/flexget/torrents/
```

## 常见问题
### 我的python版本是2.X如何使用？
<span id="version"></span>
本插件只支持Python 3.X或Python 2.7版本，其他版本不可用，请卸载Flexget后使用Python3重装
```bash
pip uninstall flexget  # 卸载
pip3 install flexget  # 使用pip3安装
```
### 目前支持哪些站点
<span id="site"></span>
如果站点禁止使用脚本爬虫，应立即停止使用本插件
- 任何未修改关键结构的nexusphp站点
- PTH
- MT（站点安全性较高，[ip或浏览器变动](#user-agent)可能无法访问）
- OB
- Sky
- School
- U2
- CHD
- TJU（禁止脚本，请勿使用）
- SSD
- OpenCD
- TTG（不支持人数筛选）
- FRDS
- Dream
- HDC（禁止脚本，无法使用）

### 如何判断站点是否支持
[判断站点以及适配站点](https://github.com/Juszoe/flexget-nexusphp/blob/master/site.md)

### 确认cookie正确，还是提示 Can't access the site. Your cookie may be wrong!
<span id="user-agent"></span>
某些站点安全性要求较高，ip或浏览器变动时无法使用cookie访问，需要重新登录。<br>
解决办法：设置 user-agent 参数与浏览器相同，查看浏览器user-agent的方法自行搜索，并保证登录ip与使用Flexget相同。

### 站点启用了Cloudflare五秒盾无法获取信息
当触发Cloudflare五秒盾通常有以下提示：
```
NexusPHP._get_info: 503 Server Error: Service Temporarily Unavailable for url
```
解决方案也很简单，可以考虑使用Flexget官方内置的插件[cfscraper](https://flexget.com/Plugins/cfscraper)
1. 首先需要安装依赖
``` bash
pip install cloudscraper
```
2. 然后启用
``` yaml
cfscraper: yes
```
**注意！绕过站点安全机制可能有风险，自行决定是否使用**


## 支持作者
<span id="donate"></span>
插件经常需要时间维护，如果本插件对你有用，可以请作者吃顿饭😉，给作者提供更多动力<br>
**ETH(Huobi):** `0x052456027321217bf10186704979bd7ac5fbc44d`<br>
**ETH:** `0x82e3ed7C4cDAabf3A98342AB4C0273C3f49EeE4D`<br>
<img width="559" alt="wechatpay" src="https://user-images.githubusercontent.com/47920609/118388150-3c97f880-b655-11eb-8801-0c2df3a0b966.png">
