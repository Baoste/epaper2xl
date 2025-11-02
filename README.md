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