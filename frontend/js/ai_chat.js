const AIChat = (() => {
  let chatMessages = null;
  let chatInput = null;
  let chatSend = null;
  let isSending = false;
  let chatCharts = [];

  let activeStatusRow = null;
  let activeAiBubble = null;
  let streamedReply = "";

  const SUGGESTION_MARKERS = [
    "你可以继续追问", "继续追问", "请继续追问",
    "💡你可以继续追问", "💡 你可以继续追问",
    "可以继续追问", "相关追问", "推荐追问",
    "你可以接着问", "接着问", "追问建议"
  ];

  const scrollToBottom = () => {
    if (chatMessages) {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  };

  const escapeHtml = (str) => {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };

  const createAvatar = (isAi) => {
    const avatar = document.createElement("div");
    avatar.className = `chat-avatar ${isAi ? "ai" : "user"}`;
    if (isAi) {
      avatar.innerHTML = `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#1a2440"/><circle cx="36" cy="44" r="5" fill="#4f8cff"/><circle cx="64" cy="44" r="5" fill="#4f8cff"/><path d="M40 62 Q50 70 60 62" stroke="#4f8cff" stroke-width="3" fill="none" stroke-linecap="round"/></svg>`;
    } else {
      avatar.textContent = "我";
    }
    return avatar;
  };

  const appendUserMessage = (text) => {
    const row = document.createElement("div");
    row.className = "chat-message-row user";
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble user";
    bubble.textContent = text;
    row.appendChild(createAvatar(false));
    row.appendChild(bubble);
    chatMessages.appendChild(row);
    scrollToBottom();
  };

  const showStatus = (text) => {
    hideStatus();
    const row = document.createElement("div");
    row.className = "chat-message-row ai status-row";
    const avatar = createAvatar(true);
    const wrap = document.createElement("div");
    wrap.className = "chat-status";
    wrap.innerHTML = `<span class="chat-status-dot"></span><span class="chat-status-text">${escapeHtml(text)}</span>`;
    row.appendChild(avatar);
    row.appendChild(wrap);
    chatMessages.appendChild(row);
    activeStatusRow = row;
    scrollToBottom();
  };

  const updateStatus = (text) => {
    if (!activeStatusRow) {
      showStatus(text);
      return;
    }
    const span = activeStatusRow.querySelector(".chat-status-text");
    if (span) span.textContent = text;
    scrollToBottom();
  };

  const hideStatus = () => {
    if (activeStatusRow) {
      activeStatusRow.remove();
      activeStatusRow = null;
    }
  };

  const createAiBubble = () => {
    hideStatus();
    const row = document.createElement("div");
    row.className = "chat-message-row ai";
    const avatar = createAvatar(true);
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble ai";
    const body = document.createElement("div");
    body.className = "chat-bubble-body";
    bubble.appendChild(body);
    row.appendChild(avatar);
    row.appendChild(bubble);
    chatMessages.appendChild(row);
    activeAiBubble = { row, bubble, body };
    streamedReply = "";
    scrollToBottom();
    return activeAiBubble;
  };

  const finalizeAiBubble = () => {
    activeAiBubble = null;
    streamedReply = "";
  };

  // 找到回复中最早的追问标记位置，返回 { index, marker }
  const findSuggestionStart = (text) => {
    let bestIdx = -1;
    let bestMarker = "";
    for (const marker of SUGGESTION_MARKERS) {
      const idx = text.indexOf(marker);
      if (idx >= 0 && (bestIdx === -1 || idx < bestIdx)) {
        bestIdx = idx;
        bestMarker = marker;
      }
    }
    return { index: bestIdx, marker: bestMarker };
  };

  // 提取正文（去掉追问部分）
  const extractBody = (text) => {
    const { index } = findSuggestionStart(text);
    const body = index >= 0 ? text.slice(0, index).trim() : text.trim();
    return body || "抱歉，我暂时无法回答这个问题。";
  };

  // 提取追问问题列表
  const extractSuggestions = (text) => {
    const { index, marker } = findSuggestionStart(text);
    if (index < 0 || !marker) return [];

    let tail = text.slice(index + marker.length);
    // 去掉 marker 后面可能跟的冒号、空格、换行、引导符号
    tail = tail.replace(/^[\s:：]+/, "");
    // 分段：优先按换行切分；如果只有一行且含多个 bullet，再按 bullet 切分
    let rawItems = tail
      .split(/\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (rawItems.length === 1 && /[·•]/.test(rawItems[0])) {
      rawItems = rawItems[0]
        .split(/[·•]/)
        .map((s) => s.trim())
        .filter(Boolean);
    }

    const questions = [];
    for (const item of rawItems) {
      const clean = item
        .replace(/^[\s·•\-*\d\.\)\]]+/, "")
        .replace(/\s+/g, " ")
        .trim();
      if (clean && /[？?]$/.test(clean)) {
        questions.push(clean);
      }
    }
    return questions;
  };

  // 获取当前应当显示在气泡里的正文（流式期间实时切掉建议部分）
  const getDisplayBody = (text) => {
    const { index } = findSuggestionStart(text);
    if (index < 0) return text;
    return text.slice(0, index);
  };

  const appendAiText = (text) => {
    if (!activeAiBubble) createAiBubble();
    streamedReply += text;
    activeAiBubble.body.textContent = getDisplayBody(streamedReply);
    scrollToBottom();
  };

  const hasChartData = (evt) => {
    if (!evt || !evt.data) return false;
    const d = evt.data;
    if (d.labels && d.labels.length) return true;
    if (d.categories && d.categories.length) return true;
    if (d.option) return true;
    return false;
  };

  const renderChartBubble = (evt) => {
    hideStatus();
    if (!hasChartData(evt)) {
      console.warn("chart 事件无有效数据，跳过", evt);
      return;
    }
    const row = document.createElement("div");
    row.className = "chat-message-row ai";
    const avatar = createAvatar(true);
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble ai chart-bubble";
    const box = document.createElement("div");
    box.className = "chat-chart";
    bubble.appendChild(box);
    row.appendChild(avatar);
    row.appendChild(bubble);
    chatMessages.appendChild(row);
    try {
      const chart = echarts.init(box);
      chatCharts.push(chart);
      chart.setOption(buildChartOption(evt.chartType, evt.data));
    } catch (err) {
      console.error("图表渲染失败:", err);
      box.textContent = "图表加载失败";
      box.style.display = "flex";
      box.style.alignItems = "center";
      box.style.justifyContent = "center";
      box.style.color = "var(--text-dim)";
    }
    scrollToBottom();
  };

  const renderSuggestions = (questions) => {
    if (!questions || !questions.length) return;
    const row = document.createElement("div");
    row.className = "chat-message-row ai suggestions-row";
    const spacer = document.createElement("div");
    spacer.className = "chat-avatar-spacer";
    const wrap = document.createElement("div");
    wrap.className = "chat-suggestions-card";
    const label = document.createElement("div");
    label.className = "chat-suggestions-label";
    label.textContent = "💡 继续追问";
    wrap.appendChild(label);
    const chips = document.createElement("div");
    chips.className = "chat-suggestions-chips";
    questions.forEach((q) => {
      const chip = document.createElement("button");
      chip.className = "chat-suggestion-chip";
      chip.type = "button";
      chip.textContent = q;
      chip.title = "点击追问";
      chip.addEventListener("click", () => sendSuggestion(q));
      chips.appendChild(chip);
    });
    wrap.appendChild(chips);
    row.appendChild(spacer);
    row.appendChild(wrap);
    chatMessages.appendChild(row);
    scrollToBottom();
  };

  const buildChartOption = (chartType, data) => {
    if (data && data.option) return data.option;
    if (chartType === "pie" && data) {
      return {
        backgroundColor: "transparent",
        tooltip: { trigger: "item", backgroundColor: "#1a2440", borderColor: "#243056", formatter: "{b}: {c} ({d}%)" },
        series: [{
          type: "pie", radius: ["35%", "65%"],
          itemStyle: { borderColor: "#131a2e", borderWidth: 2 },
          label: { color: CONFIG.THEME ? CONFIG.THEME.textColor : "#e6ecff" },
          data: data.labels.map((l, i) => ({
            name: l, value: data.counts[i],
            itemStyle: { color: (CONFIG.THEME ? CONFIG.THEME.color : ["#4f8cff", "#36d1b7", "#ff5c7c", "#f5a623"])[i % 4] }
          }))
        }]
      };
    }
    return {
      backgroundColor: "transparent",
      grid: { top: 30, left: 50, right: 20, bottom: 30 },
      tooltip: { trigger: "axis", backgroundColor: "#1a2440", borderColor: "#243056" },
      xAxis: { type: "category", data: data.categories, axisLabel: { color: CONFIG.THEME ? CONFIG.THEME.textColor : "#e6ecff" } },
      yAxis: { type: "value", axisLabel: { color: CONFIG.THEME ? CONFIG.THEME.textColor : "#e6ecff" }, splitLine: { lineStyle: { color: CONFIG.THEME ? CONFIG.THEME.splitLine : "#243056" } } },
      series: [{ type: "bar", data: data.values, itemStyle: { color: CONFIG.THEME ? CONFIG.THEME.color[0] : "#4f8cff" }, barWidth: "55%" }]
    };
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
    if (/你好|hi|hello/i.test(question)) {
      return "你好！我是 AI 智能助手，可以帮你分析电商用户行为数据，例如询问销量趋势、品类热度或用户分层。";
    }
    return replies[Math.floor(Math.random() * replies.length)];
  };

  const finishReply = () => {
    if (activeAiBubble && activeAiBubble.body) {
      activeAiBubble.body.textContent = extractBody(streamedReply);
    }
    const suggestions = extractSuggestions(streamedReply);
    finalizeAiBubble();
    renderSuggestions(suggestions);
  };

  const mockSend = async (question) => {
    showStatus("正在思考...");
    await new Promise((r) => setTimeout(r, 600));

    const reply = getMockReply(question) + "\n\n你可以继续追问：\n· 12月12日销量激增是否伴随加购率或转化率的同步跃升？\n· 能否对比该日与前后日的加购→购买转化率？\n· 同期DAU数据是否也出现峰值？";
    createAiBubble();
    for (let i = 0; i < reply.length; i++) {
      appendAiText(reply[i]);
      await new Promise((r) => setTimeout(r, 12));
    }
    finishReply();

    if (/趋势|图|排行|热度|分布|rfm/i.test(question)) {
      await new Promise((r) => setTimeout(r, 300));
      const isPie = /分布|rfm/i.test(question);
      renderChartBubble({
        chartType: isPie ? "pie" : "bar",
        data: isPie
          ? { labels: ["重要价值用户", "重要保持用户", "一般价值用户", "浏览型用户"], counts: [12500, 8900, 15800, 7200] }
          : { categories: ["无线蓝牙耳机", "智能手表", "机械键盘", "游戏鼠标", "便携音箱"], values: [12580, 9850, 7620, 6450, 5380] }
      });
    }
  };

  const realSend = async (question) => {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const raw of lines) {
        const line = raw.trim();
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;

        let evt;
        try { evt = JSON.parse(payload); } catch (e) { continue; }

        if (evt.type === "status") {
          updateStatus(evt.content || "AI 正在思考...");
        } else if (evt.type === "text") {
          const content = evt.content || "";
          if (!content.trim() && !activeAiBubble) continue;
          appendAiText(content);
        } else if (evt.type === "chart") {
          finalizeAiBubble();
          renderChartBubble(evt);
        } else if (evt.type === "done") {
          hideStatus();
        }
      }
    }

    if (streamedReply.trim()) {
      finishReply();
    } else {
      finalizeAiBubble();
    }
  };

  const sendSuggestion = (text) => {
    if (!text || isSending) return;
    isSending = true;
    chatSend.disabled = true;
    appendUserMessage(text);
    chatInput.value = "";

    const payload = `分析一下：${text}`;
    (async () => {
      try {
        if (CONFIG.USE_MOCK) {
          await mockSend(payload);
        } else {
          await realSend(payload);
        }
      } catch (err) {
        console.error("Chat error:", err);
        if (!activeAiBubble) createAiBubble();
        appendAiText("网络异常，请稍后重试。");
        finalizeAiBubble();
      } finally {
        isSending = false;
        chatSend.disabled = false;
        scrollToBottom();
      }
    })();
  };

  const sendMessage = () => {
    const question = chatInput.value.trim();
    if (!question || isSending) return;

    isSending = true;
    chatSend.disabled = true;
    appendUserMessage(question);
    chatInput.value = "";

    (async () => {
      try {
        if (CONFIG.USE_MOCK) {
          await mockSend(question);
        } else {
          await realSend(question);
        }
      } catch (err) {
        console.error("Chat error:", err);
        if (!activeAiBubble) createAiBubble();
        appendAiText("网络异常，请稍后重试。");
        finalizeAiBubble();
      } finally {
        isSending = false;
        chatSend.disabled = false;
        scrollToBottom();
      }
    })();
  };

  const init = () => {
    chatMessages = document.getElementById("chat-messages");
    chatInput = document.getElementById("chat-input");
    chatSend = document.getElementById("chat-send");
    if (!chatMessages || !chatInput || !chatSend) {
      console.warn("AIChat 初始化失败：未找到聊天 DOM 元素");
      return;
    }

    let isComposing = false;
    chatInput.addEventListener("compositionstart", () => { isComposing = true; });
    chatInput.addEventListener("compositionend", () => { isComposing = false; });

    chatSend.addEventListener("click", sendMessage);
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !isComposing && !e.isComposing) {
        e.preventDefault();
        sendMessage();
      }
    });

    window.addEventListener("resize", () => chatCharts.forEach((c) => c.resize()));

    // 欢迎语
    createAiBubble();
    activeAiBubble.body.textContent = "你好！我是 AI 智能助手，可以帮你分析电商数据。试试问我「上周销量趋势」或「RFM 分布」。";
    finalizeAiBubble();
  };

  return { init, sendMessage };
})();
