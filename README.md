# flexget-nexusphp
Flexget插件，增强对NexusPHP的过滤
过滤条件包括种子优惠信息（free等）、做种者情况、下载者情况
- `注意：本插件为测试版，未经过完全的测试`
- [站点支持列表](#site)

## 运行环境
- 已安装flexget
- python 3.X [python2解决方案](#py2)

## 安装插件
1. 下载插件 [nexusphp.py](https://github.com/Juszoe/flexget-nexusphp/releases)
2. 在Flexget配置文件夹下新建plugins文件夹，例如：
```
~/.flexget/plugins/  # Linux
C:\Users\<YOURUSER>\flexget\plugins\  # Windows
```
3. 将插件拷贝至plugins
4. 若启用了Web-UI或守护进程，则重启flexget重新加载配置

## 使用
1. 编辑flexget配置文件，添加nexusphp选项，按照需要进行配置
``` yaml
nexusphp:
  cookie: 'you_cookie'  # 必填
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
  hr: no  # 是否下载HR 选填
```
2. 为rss的other_fields字段添加link属性
``` yaml
rss: 
  url: https://www.example.com/rss.xml
  other_fields:
    - link
```
3. 启动flexget
``` bash
flexget execute
```

## 详细配置
### cookie
网站cookie，必须填写
### discount
优惠类型，默认不限制优惠类型。
列表类型，Flexget会只下载含有列表内优惠类型的种子。
有效值：`free 2x 2x50% 2xfree 50% 30%`
`注意：x为英文字母`
### seeders
做种情况，包含字段`min` `max`。做种人数超出范围的，Flexget将不会下载
#### `min`
数字，最小做种人数，默认不限制
#### `max`
数字，最大做种人数，默认不限制
### leechers
下载情况，包含字段`min` `max` `max_complete`。下载人数超出范围的，Flexget将不会下载
#### `min`
数字，最小下载人数，默认不限制
#### `max`
数字，最大下载人数，默认不限制
#### `max_complete`
小数，范围`0-1.0` 下载者中最大完成度，超过这个值将不下载，默认为1
### hr
yes或no，是否下载HR，默认不考虑HR，即可能下载到HR

## 完整配置示例
### 免费热种
``` yaml
tasks:
  my-free-task:
    rss: 
      url: https://www.example.com/rss.xml
      other_fields:
        - link
    nexusphp:
      cookie: 'you_cookie'
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
``` yaml
tasks:
  my-hot-task:
    rss: 
      url: https://www.example.com/rss.xml
      other_fields:
        - link
    nexusphp:
      cookie: 'you_cookie'
      seeders:
        min: 1
      leechers:
        min: 20
    download: ~/flexget/torrents/
```
### 避免HR
``` yaml
tasks:
  no-hr-task:
    rss: 
      url: https://www.example.com/rss.xml
      other_fields:
        - link
    nexusphp:
      cookie: 'you_cookie'
      hr: no
    download: ~/flexget/torrents/
```

## 常见问题
#### 我的python版本是2.X如何使用？
<span id="py2"></span>
本插件只支持python 3.X版本，请卸载flexget后使用python3重装
```bash
pip uninstall flexget  # 卸载
pip3 install flexget  # 使用pip3安装
```
#### 目前支持哪些站点
<span id="site"></span>
以下站点名使用别称或简称，欢迎反馈更多可用或不可用的站点
- 任何未修改关键结构的nexusphp站点
- 铂金家
- 馒头（站点安全性较高，使用flexget ip与登录ip不同时可能无法使用）
- nice
- 菠萝
- OB
- 天空
- 学校

#### 如何判断站点是否支持
[判断站点以及适配站点](https://github.com/Juszoe/flexget-nexusphp/blob/master/site.md)