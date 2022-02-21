# HEED
High Efficiency Elective Dominator (with GUI)



## 基本使用流程

1. 选择使用构建好的版本或者从源码运行
     - 如果要从源码运行，请确认 Python 版本 ≥ 3.6，然后 `pip install -r requirements.txt`，已在 Windows 10 和 Ubuntu 20.04（GNOME 桌面环境）上测试可用
     - 如果要运行构建好的版本，只需要一个 64 位的 Windows，然后 [从 releases 里进行一个下载](https://github.com/xmcp/HEED-GUI/releases)，注意这样将**无法支持识别验证码和推送通知**功能（其实源码版也不支持，但是留了相应接口允许你配置，参见后面 “高级功能”）
2. 运行 `main.pyw`，输入学号和密码
   - 如果你有双学位，请在学号后面加 `@bzx`（表示主修）或者 `@bfx`（表示辅双），例如 `1900012345@bfx` 
3. 你将看到一个主窗口（用于操作）和一个日志窗口（用于查看工作状态）
4. 点击主窗口的 `Add Bot` 一到三次
   - 将提示输入验证码，请手动输入然后按回车确认（点击 `Next Captcha` 跳过当前验证码），或者参阅后面 ”高级功能“ 的 ”自动识别验证码“
   - 日志窗口将出现一些形如 “Bot 1 [idle]” 的内容，表示这个 Bot 已经可用于选课了
5. 点击主窗口的 `Refresh`，将显示课程列表
6. 在课程列表里双击来选课（未满）或加到待选列表（已满）
   - 右边那个窄的列表是待选课程列表，双击删除
7. 勾选上 `Auto` 开始自动选课
   - 为了使结果更加清晰，`Auto` 模式下将仅显示待选课程，如果需要添加其他课程请取消勾选 `Auto` 然后再点一下 `Refresh`
8. 保持程序运行
   - 可以在主窗口的标题栏看到最近一次刷新的时间
   - 可以在日志窗口观察状态，或者等待推送通知（参阅后面 ”高级功能“ 的 “推送通知”）
   - 如果没有设置自动识别验证码，Session 过期后 Bot 会死掉，此时需要再点击 `Add Bot` 并重新输入验证码，请时刻关注日志窗口或者推送通知；如果设置了自动识别验证码，Session 过期后 Bot 会自动重启，无需人工操作
9. 为防止误操作，**先取消选择 `Auto` 才能点击主窗口的关闭按钮**



## 高级功能

### 自动识别验证码

请自己想办法接入商业 API 或者凹模型。

修改 `captcha.py`，函数 `recognize` 接收一个 `PIL.Image` 类型的图片作为参数，返回一个字符串作为识别结果。

配置完后勾选主窗口的 `Captcha` 来启用自动识别验证码。

为了方便调试模型，还有一个 `aux_captcha_widget.pyw` 脚本可以单独测试验证码识别功能。



### 推送通知

请自己想办法接入推送 API。

修改 `notifier.py`，方法 `_do_notif` 接收一个字符串类型的消息内容。目前给的例子是飞书的机器人发消息 API。

配置完后勾选主窗口的 `Notif` 来启用推送通知。

勾选后会立即发送一条 “服务已启动” 来帮助你测试推送通知是否功能正常。



### 预先输入待选列表

如果你想预先输入待选课程列表，请在当前目录（即程序的 Working Directory）下创建文件 `wishlist.txt`。

文件内容是一行一个要选的课程，格式是 `课程名称|班号`，例如 `计算机系统导论|1`。请注意不要有多余的空格。

这些课程将在程序启动时就添加到待选列表里。



### 自动刷新参数配置

`Intv` 用于设置自动刷新间隔（毫秒），最低限制是 5000。

`Timeout` 用于设置网络请求超时时间（毫秒）。

`Verbose` 用于在日志窗口里显示更详细的内容。



## 使用提示

- **不要把 `Intv` 设置的太低**
  - 选课网有缓存机制，设置为每秒刷新好几次只是每秒读好几次缓存的数据，并不会改善成功率
  - 而且经验表明，刷新频率过快会被禁止登录一段时间，得不偿失
  - 一般来说，5000ms 是一个相对于缓存时间来说足够快的刷新频率，也是默认的最快频率
- **不要点 `Add Bot` 太多次**
  - 每个 Bot 对应一个选课网的 Session，经验表明超过 5 个的话可能会被选课网限制
  - 一般来说，如果你设置了自动识别验证码，开 3 个 Bot 就够了；如果是手动识别验证码，开 5 个 Bot 就够了
- 减少选课计划中的课程数可以提高网络不佳时的成功率
  - 建议把补退选的列表控制在一页，这样程序不需要翻页
- 本软件会跳过人数为 0 的课
  - 这是因为选课系统偶尔把选课人数错误地显示为 0
  - 如果你确实要选一门 0 人选的课，请直接去选课网上操作
- “请不要使用刷课机刷课”
  - **使用本软件的一切后果自负**
  - 不要问 “本软件是否会把课退光” 之类的问题，如有任何疑惑请直接看代码



## LICENSE

```
Copyright (C) 2022 xmcp

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
