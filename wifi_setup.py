from flask import Flask, render_template, request, jsonify
import os, time, subprocess, threading, signal, sys, re

app = Flask(__name__, template_folder="templates")

# ---------------------------------------------
# 工具函数
# ---------------------------------------------
def get_ip():
    try:
        out = subprocess.getoutput("hostname -I").strip()
        return out.split()[0] if out else ""
    except Exception:
        return ""

def check_connected(ssid):
    connected_ssid = subprocess.getoutput("iwgetid -r").strip()
    ip = get_ip()
    return (connected_ssid == ssid and ip != ""), ip

def scan_wifi():
    """扫描附近 Wi-Fi SSID 列表"""
    try:
        output = subprocess.getoutput("sudo iwlist wlan0 scan | grep 'ESSID'")
        ssids = re.findall(r'ESSID:"(.*?)"', output)
        ssids = sorted(list(set(filter(None, ssids))))
        return ssids
    except Exception:
        return []

# ---------------------------------------------
# Wi-Fi 连接逻辑
# ---------------------------------------------
status_info = {"ssid": "", "connected": False, "ip": ""}

def connect_wifi(ssid, psk):
    global status_info
    print(f"try to connect to {ssid} ...")
    status_info.update({"ssid": ssid, "connected": False, "ip": ""})

    # === Step 1: 检查当前是否已连接到目标 Wi-Fi 且网络可用 ===
    connected_ssid = subprocess.getoutput("iwgetid -r").strip()
    if connected_ssid == ssid:
        ip = get_ip()
        if os.system("ping -c 1 -W 1 8.8.8.8 > /dev/null 2>&1") == 0:
            print(f"✅ 已经连接到 {ssid}, IP: {ip}")
            status_info.update({"connected": True, "ip": ip})
            return
        else:
            print("⚠️ 当前 Wi-Fi 无法访问网络，将重新连接...")

    # === Step 2: 检查并更新配置文件 ===
    wpa_conf_path = "/etc/wpa_supplicant/wpa_supplicant.conf"
    os.system(f"sudo chmod 666 {wpa_conf_path}")

    with open(wpa_conf_path, "r") as f:
        conf_lines = f.readlines()

    new_block = [
        "network={\n",
        f'    ssid="{ssid}"\n',
        f'    psk="{psk}"\n',
        "}\n",
    ]

    # 查找是否已有该 ssid
    start_idx, end_idx = None, None
    for i, line in enumerate(conf_lines):
        if f'ssid="{ssid}"' in line:
            # 找到包含该 ssid 的 network 块
            for j in range(i, -1, -1):
                if conf_lines[j].strip().startswith("network={"):
                    start_idx = j
                    break
            for j in range(i, len(conf_lines)):
                if conf_lines[j].strip().startswith("}"):
                    end_idx = j
                    break
            break

    if start_idx is not None and end_idx is not None:
        print(f"✏️ 更新已有 Wi-Fi 配置: {ssid}")
        conf_lines[start_idx:end_idx + 1] = new_block
    else:
        print(f"🆕 添加新的 Wi-Fi 配置: {ssid}")
        if not conf_lines or conf_lines[-1].strip() != "":
            conf_lines.append("\n")
        conf_lines.extend(new_block)

    # 写回文件
    with open(wpa_conf_path, "w") as f:
        f.writelines(conf_lines)

    os.system(f"sudo chmod 600 {wpa_conf_path}")

    # === Step 3: 重新加载配置并尝试连接 ===
    os.system("sudo wpa_cli -i wlan0 reconfigure")
    print("📡 正在检测连接状态...")

    for _ in range(12):  # 最多等待约 24 秒
        ok, ip = check_connected(ssid)
        if ok:
            # 再次确认外网是否可访问
            if os.system("ping -c 1 -W 1 8.8.8.8 > /dev/null 2>&1") == 0:
                print(f"✅ 成功连接到 {ssid}, IP: {ip}")
                # 连接成功后关闭热点
                os.system("sudo systemctl stop hostapd")
                os.system("sudo systemctl stop dnsmasq")
                os.system("sudo systemctl restart networking")
                status_info.update({"connected": True, "ip": ip})
                return
            else:
                print("⚠️ 已连接但无法访问外网，保留热点供重新配置。")
                break
        time.sleep(2)

    print("❌ 连接失败，保持热点供重新配置。")
    status_info.update({"connected": False, "ip": ""})

# ---------------------------------------------
# Flask 路由
# ---------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    msg = ""
    ssids = scan_wifi()

    if request.method == "POST":
        ssid = request.form.get("ssid")
        psk = request.form.get("psk")
        if not ssid or not psk:
            msg = "⚠️ 请输入完整的 Wi-Fi 名称和密码。"
        else:
            msg = f"正在连接 Wi-Fi <b>{ssid}</b>..."
            threading.Thread(target=connect_wifi, args=(ssid, psk), daemon=True).start()
            msg += "<br>⏳ 请等待连接完成，网页将自动跳转。"

    ip = get_ip() or "192.168.4.1"
    msg += f"<br><br>🌐 当前树莓派IP: <b>{ip}</b>"
    return render_template("index.html", msg=msg, ssids=ssids)

@app.route("/status")
def status():
    return jsonify(status_info)

@app.route("/scan")
def scan():
    ssids = scan_wifi()
    return jsonify({"ssids": ssids})

# ---------------------------------------------
# 退出信号
# ---------------------------------------------
def graceful_exit(signum, frame):
    print("\n正在退出 Flask 服务...")
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)

if __name__ == "__main__":
    ip = get_ip() or "0.0.0.0"
    print(f"Flask 运行中，请访问: http://{ip}:80")
    app.run(host="0.0.0.0", port=80)
