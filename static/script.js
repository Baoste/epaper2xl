document.getElementById("uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const msgBox = document.getElementById("msg");
  msgBox.innerText = "⏳ 正在上传并处理...";
  msgBox.style.color = "white";

  try {
    const res = await fetch("/upload", {
      method: "POST",
      body: formData
    });

    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      msgBox.innerText = "⚠️ 服务返回异常：" + text.slice(0, 100);
      msgBox.style.color = "orange";
      return;
    }

    if (data.status === "ok") {
      msgBox.innerText = "✅ 成功：" + (data.message || "已显示！");
      msgBox.style.color = "green";
    } else {
      msgBox.innerText = "❌ 失败：" + (data.message || "未知错误");
      msgBox.style.color = "red";
    }
  } catch (err) {
    msgBox.innerText = "⚠️ 网络错误：" + err;
    msgBox.style.color = "orange";
  }
});

document.getElementById("shutdownBtn").addEventListener("click", async () => {
  if (!confirm("确定要关闭树莓派吗？")) return;
  document.getElementById("msg").innerText = "⚠️ 正在关机...";
  try {
    const res = await fetch("/shutdown", { method: "POST" });
    const data = await res.json();
    document.getElementById("msg").innerText = "💤 " + data.message;
  } catch (err) {
    document.getElementById("msg").innerText = "❌ 关机失败: " + err;
  }
});

document.getElementById("playMovie").addEventListener("click", async () => {
  const msg = document.getElementById("msg");
  msg.innerText = "🎬 正在启动电影播放...";
  try {
    const res = await fetch("/play_movie", { method: "POST" });
    const data = await res.json();
    msg.innerText = "🎞️ " + data.message;
  } catch (err) {
    msg.innerText = "❌ 播放失败: " + err;
  }
});