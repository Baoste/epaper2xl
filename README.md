## 网页拍摄

控制面板的“拍摄照片”按钮调用树莓派摄像头 0，拍摄后在页面显示照片。
默认使用 1296×972 JPEG、质量 85，预热 1.5 秒，整个拍摄进程最多等待 20 秒。
照片直接传给浏览器，不保存到 SD 卡；刷新页面后预览清空。拍摄不会触发墨水屏刷新。

依赖系统命令 `rpicam-still`，不需要在 Python 虚拟环境中安装摄像头库。
可先在树莓派上检查：

```bash
command -v rpicam-still
rpicam-still --camera 0 --nopreview --timeout 1500 --width 1296 --height 972 --output /tmp/camera-test.jpg
```

若命令缺失，可安装 `sudo apt install rpicam-apps`。
将更新后的 `server.py`、`templates/index.html`、`static/script.js` 和 `static/style.css`
同步到树莓派后，执行 `sudo systemctl restart epaper.service`，并强制刷新网页。
若拍摄失败，关闭正在使用摄像头的程序（例如 `rpicam-hello`），并查看日志：

```bash
journalctl -u epaper.service -n 50 --no-pager
```

摄像头参数说明：[Raspberry Pi 官方文档](https://www.raspberrypi.com/documentation/computers/camera_software.html)。

## 打开关闭 systemd
```bash
# 开机自启
sudo systemctl enable epaper.service
# 开启/停止服务
sudo systemctl start epaper.service
sudo systemctl stop epaper.service
# 禁止开机自启
sudo systemctl disable epaper.service
# 查看状态
sudo systemctl status epaper.service
```

## 有办法将 http://192.168.1.25/ 改成好记的地址吗

**使用 mDNS**
也就是 .local 域名，例如：
http://raspberrypi.local/
http://epaper.local/

**操作步骤**
在树莓派安装 Avahi 服务（mDNS 解析器）
```bash
sudo apt install avahi-daemon -y
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon
```
修改主机名（比如改成 epaper2xl）
```bash
sudo hostnamectl set-hostname epaper2xl
```
重启 Avahi
```bash
sudo systemctl restart avahi-daemon
```
现在可以用：
http://epaper2xl.local/
访问网页（只要在同一个局域网内）。如果 Windows 无法访问 .local，安装 Bonjour。
