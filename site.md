# 判断站点支持程度
- 若发现日志输出大量none，可能该站点不支持，请联系开发者适配
```bash
REJECTED: `XXX` by nexusphp plugin because none does not match discount
```
- 该站点结构和其他站点区别较大，可能不支持

# 适配站点
## 自行适配
1. 在详情页面的HTML代码中寻找相关信息，如：
```html
<h1 align="center" id="top">XXX 2006 1080p<b>[<font class="free">免费</font>]</b></h1>
<h1 align="center" id="top">XXX 2006 1080p<b>[<font class="twoup">2X</font>]</b></h1>
<h1 align="center" id="top">XXX 2006 1080p<b>[<font class="twoupfree">2X免费</font>]</b></h1>
<h1 align="center" id="top">XXX 2006 1080p<b>[<font class="thirtypercent">30%</font>]</b></h1>
<h1 align="center" id="top">XXX 2006 1080p<b>[<font class="halfdown">50%</font>]</b></h1>
<h1 align="center" id="top">XXX 2006 1080p<b>[<font class="twouphalfdown">2X50%</font>]</b></h1>
```
选择其中的类名作为标识，即 `free twoup twoupfree thirtypercent halfdown twouphalfdown`
2. 在配置文件添加适配选项adopter
```yaml
nexusphp:
    adopter:
      free: free
      2x: twoup
      2xfree: twoupfree
      30%: thirtypercent
      50%: halfdown
      2x50%: twouphalfdown
```
## 开发者适配
请联系开发者并提供以下信息：
- 站点名
- Flexget相关输出日志
- 站点关键HTML结构截图，只需要free信息附近的HTML代码，
注意是详情页面的代码，而非列表里的

`注意：提供信息时注意passkey`