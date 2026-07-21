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

  const getMockReply = (question) => {
    const replies = [
      "根据数据分析，本周销量最高的商品是无线蓝牙耳机，共售出 12,580 件，环比增长 18.3%。",
      "当前日活跃用户数为 12,345，较昨日下降 3.0%。建议关注用户留存策略。",
      "转化漏斗显示，从浏览到购买的转化率为 8%，主要流失环节在加购到购买阶段。",
      "RFM 分析显示，重要价值用户占比约 12%，建议针对这部分用户推出专属优惠活动。",
      "近 7 日 PV 数据呈现上升趋势，今日达到 165,000，创本周新高。",
      "商品热度榜单中，智能穿戴类产品表现亮眼，智能手表排名第二。",
      "数码品类转化率环比下降 12%，建议加大促销力度以挽回流失。",
      "新用户占比约 15.8%，建议优化首单优惠策略以提升新用户转化率。"
    ];
    if (/你好|hi|hello/i.test(question)) return "你好！我是 AI 智能助手，可以帮你分析电商用户行为数据，例如询问销量趋势、品类热度或用户分层。";
    return replies[Math.floor(Math.random() * replies.length)];
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
          label: { color: CONFIG.THEME.textColor },
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
    bubble.className = "bubble ai";
    const box = document.createElement("div");
    box.className = "chat-chart";
    bubble.appendChild(box);
    chatMessages.appendChild(bubble);
    const chart = echarts.init(box);
    chatCharts.push(chart);
    chart.setOption(buildChartOption(evt.chartType, evt.data));
    scrollToBottom();
  };

  // ===== Mock 模式：模拟逐字流式 + 可选图表 =====
  const mockSend = async (question, aiBubble) => {
    const reply = getMockReply(question);
    let acc = "";
    for (let i = 0; i < reply.length; i++) {
      acc += reply[i];
      aiBubble.innerHTML = acc + "<span class='cursor'>▌</span>";
      scrollToBottom();
      await new Promise(r => setTimeout(r, 18));
    }
    aiBubble.innerHTML = acc;

    if (/趋势|图|排行|热度|分布|rfm/i.test(question)) {
      await new Promise(r => setTimeout(r, 300));
      const isPie = /分布|rfm/i.test(question);
      renderChartBubble({
        chartType: isPie ? "pie" : "bar",
        data: isPie
          ? { labels: ["重要价值用户", "重要保持用户", "一般价值用户", "浏览型用户"],
              counts: [12500, 8900, 15800, 7200] }
          : { categories: ["无线蓝牙耳机", "智能手表", "机械键盘", "游戏鼠标", "便携音箱"], values: [12580, 9850, 7620, 6450, 5380] }
      });
    }
  };

  // ===== 真实模式：POST /api/chat，解析 SSE 事件流 =====
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
      if (CONFIG.USE_MOCK) {
        await mockSend(question, aiBubble);
      } else {
        await realSend(question, aiBubble);
      }
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
