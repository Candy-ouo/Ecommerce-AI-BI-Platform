const AIChat = (() => {
  let chatMessages = null;
  let chatInput = null;
  let chatSend = null;
  let isSending = false;
  let chatCharts = [];   // 对话内图表实例，随窗口缩放

  const scrollToBottom = () => {
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  const addBubble = (text, type) => {
    if (!chatMessages) return null;
    const bubble = document.createElement("div");
    bubble.className = `bubble ${type}`;
    bubble.innerHTML = text;
    chatMessages.appendChild(bubble);
    scrollToBottom();
    return bubble;
  };

  // 根据后端 chart 事件构建 ECharts option
  const buildChartOption = (chartType, data) => {
    if (data && data.option) return data.option;
    if (chartType === "pie" && data) {
      return {
        backgroundColor: "transparent",
        tooltip: { trigger: "item", backgroundColor: "#1a2440", borderColor: "#243056", formatter: "{b}: {c} ({d}%)" },
        series: [{
          type: "pie", radius: ["35%", "65%"],
          itemStyle: { borderColor: "#131a2e", borderWidth: 2 },
          label: {
            show: true,
            position: "outside",
            color: CONFIG.THEME.textColor,
            fontSize: 11,
            formatter: "{b}: {d}%"
          },
          labelLine: {
            show: true,
            length: 15,
            length2: 20,
            lineStyle: {
              color: CONFIG.THEME.textColor,
              width: 1
            }
          },
          data: data.labels.map((l, i) => ({
            name: l, value: data.counts[i],
            itemStyle: { color: CONFIG.THEME.color[i % CONFIG.THEME.color.length] }
          }))
        }]
      };
    }
    // 默认柱状图
    return {
      backgroundColor: "transparent",
      grid: { top: 30, left: 50, right: 20, bottom: 30 },
      tooltip: { trigger: "axis", backgroundColor: "#1a2440", borderColor: "#243056" },
      xAxis: { type: "category", data: data.categories, axisLabel: { color: CONFIG.THEME.textColor } },
      yAxis: { type: "value", axisLabel: { color: CONFIG.THEME.textColor }, splitLine: { lineStyle: { color: CONFIG.THEME.splitLine } } },
      series: [{ type: "bar", data: data.values, itemStyle: { color: CONFIG.THEME.color[0] }, barWidth: "55%" }]
    };
  };

  const renderChartBubble = (evt) => {
    const bubble = document.createElement("div");
    bubble.className = "bubble ai has-chart";
    const box = document.createElement("div");
    box.className = "chat-chart";
    bubble.appendChild(box);
    chatMessages.appendChild(bubble);
    scrollToBottom();
    setTimeout(() => {
      const chart = echarts.init(box);
      chatCharts.push(chart);
      chart.setOption(buildChartOption(evt.chartType, evt.data));
      chart.resize();
    }, 100);
  };

  // POST /api/chat，解析 SSE 事件流
  const realSend = async (question, aiBubble) => {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let reply = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // 保留未完成的半行

      for (const raw of lines) {
        const line = raw.trim();
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;

        let evt;
        try { evt = JSON.parse(payload); } catch (e) { continue; }

        if (evt.type === "text") {
          reply += evt.content;
          aiBubble.innerHTML = reply + "<span class='cursor'>▌</span>";
          scrollToBottom();
        } else if (evt.type === "chart") {
          aiBubble.innerHTML = reply; // 结束文字光标
          renderChartBubble(evt);
        } else if (evt.type === "done") {
          break;
        }
      }
    }

    aiBubble.innerHTML = reply || "抱歉，我暂时无法回答这个问题。";
  };

  const sendMessage = async () => {
    const question = chatInput.value.trim();
    if (!question || isSending) return;

    isSending = true;
    chatSend.disabled = true;
    addBubble(question, "user");
    chatInput.value = "";

    const aiBubble = addBubble("<span class='cursor'>▌</span>", "ai");

    try {
      await realSend(question, aiBubble);
    } catch (err) {
      console.error("Chat error:", err);
      aiBubble.innerHTML = "网络异常，请稍后重试。";
    } finally {
      isSending = false;
      chatSend.disabled = false;
      scrollToBottom();
    }
  };

  const init = () => {
    chatMessages = document.getElementById("chat-messages");
    chatInput = document.getElementById("chat-input");
    chatSend = document.getElementById("chat-send");
    if (!chatMessages || !chatInput || !chatSend) {
      console.warn("AIChat 初始化失败：未找到聊天 DOM 元素");
      return;
    }

    chatSend.addEventListener("click", sendMessage);
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendMessage();
    });

    window.addEventListener("resize", () => chatCharts.forEach(c => c.resize()));

    addBubble("你好！我是 AI 智能助手，可以帮你分析电商数据。试试问我「上周销量趋势」或「RFM 分布」。", "ai");
  };

  return { init, sendMessage };
})();
