const Main = (() => {
  let refreshTimer = null;
  let topDataCache = null;
  let topMetric = "pv";
  let _isLoading = false;
  const statusDot = document.getElementById("status-dot");

  const updateClock = () => {
    const now = new Date();
    const timeStr = now.toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
    const clockEl = document.getElementById("clock");
    if (clockEl) clockEl.textContent = timeStr;
  };

  const updateStatus = (connected) => {
    if (statusDot) {
      statusDot.style.background = connected ? "#36d1b7" : "#ff5c7c";
      statusDot.style.boxShadow = connected ? "0 0 8px #36d1b7" : "0 0 8px #ff5c7c";
      statusDot.title = connected ? "数据连接正常" : "数据连接断开";
    }
  };

  const retry = async (fn, retries = 3, delay = 2000) => {
    for (let i = 0; i < retries; i++) {
      try {
        return await fn();
      } catch (err) {
        if (i < retries - 1) {
          console.warn(`Retry ${i + 1}/${retries} failed:`, err.message);
          await new Promise(r => setTimeout(r, delay));
        } else {
          throw err;
        }
      }
    }
  };

  const loadData = async () => {
    if (_isLoading) return;
    _isLoading = true;
    updateStatus(true);
    try {
      // 第一阶段：加载并渲染快接口（KPI / 趋势 / 漏斗 / 晨报）
      const fastCalls = [
        { key: "kpi", fn: () => API.get("/api/kpi/cards"), render: (d) => Charts.renderKPI(d) },
        { key: "trend", fn: () => API.get(`/api/trend/active?days=7&category=${getCategory()}`), render: (d) => Charts.renderTrend(d) },
        { key: "funnel", fn: () => API.get("/api/funnel"), render: (d) => Charts.renderFunnel(d) },
        { key: "reportLatest", fn: () => API.get("/api/report/latest"), render: null },
        { key: "reportHistory", fn: () => API.get("/api/report/history?days=7"), render: null },
      ];

      const fastResults = await Promise.allSettled(fastCalls.map(c => retry(c.fn)));
      fastResults.forEach((result, idx) => {
        const { key, render } = fastCalls[idx];
        if (result.status === "fulfilled") {
          if (render) render(result.value);
        } else {
          console.warn(`模块 ${key} 加载失败:`, result.reason?.message);
        }
      });

      const reportLatest = fastResults[3].status === "fulfilled" ? fastResults[3].value : null;
      const reportHistory = fastResults[4].status === "fulfilled" ? fastResults[4].value : null;
      renderReport(reportLatest, reportHistory);

      // 第二阶段：独立加载慢接口（Hive 查询耗时较长，不阻塞快接口渲染）
      loadSlowModules();
    } catch (err) {
      console.error("Data load failed:", err);
      updateStatus(false);
    } finally {
      _isLoading = false;
      const overlay = document.getElementById("loading-overlay");
      if (overlay) overlay.style.display = "none";
    }
  };

  const loadSlowModules = async () => {
    // 商品热度
    setModuleLoading("chart-top", "商品热度加载中…");
    try {
      const topData = await API.get("/api/top/items?limit=10");
      topDataCache = topData;
      Charts.renderTopProducts(topDataCache, topMetric);
    } catch (err) {
      console.warn("商品热度加载失败:", err.message);
      setModuleLoading("chart-top", "商品热度加载失败");
    }

    // RFM
    setModuleLoading("chart-rfm", "RFM 分布加载中…");
    try {
      const rfmData = await API.get("/api/rfm/dist");
      Charts.renderRFM(rfmData);
    } catch (err) {
      console.warn("RFM 分布加载失败:", err.message);
      setModuleLoading("chart-rfm", "RFM 分布加载失败");
    }

    // 个性化推荐
    try {
      const recommendData = await API.get("/api/recommend?user_id=98047837");
      Charts.renderRecommend(recommendData);
    } catch (err) {
      console.warn("个性化推荐加载失败:", err.message);
    }
  };

  const setModuleLoading = (chartId, text) => {
    const dom = document.getElementById(chartId);
    if (!dom) return;
    // 如果已经渲染了图表，不覆盖
    if (dom.getAttribute("_echarts_instance_")) return;
    dom.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-dim);font-size:12px;">${text}</div>`;
  };

  const parseReportSections = (text) => {
    const sections = [];
    const regex = /\(([a-c])\)\s*([^\n]+)\n?([\s\S]*?)(?=\n?\([a-c]\)|$)/g;
    let m;
    while ((m = regex.exec(text)) !== null) {
      sections.push({ key: m[1], title: m[2].trim(), body: m[3].trim() });
    }
    if (sections.length === 0) {
      sections.push({ key: "a", title: "核心指标概览", body: text });
    }
    return sections;
  };

  const formatReportBody = (body) => {
    return body
      .split(/\n+/)
      .map(line => line.trim())
      .filter(line => line)
      .map(line => `<p>${line.replace(/^(\d+\.\s*)/, "<b>$1</b>")}</p>`)
      .join("");
  };

  const buildReportHtml = (content) => {
    const secMap = {
      a: { cls: "overview", icon: "📊", title: "核心指标概览" },
      b: { cls: "warning", icon: "⚠️", title: "异常预警" },
      c: { cls: "suggestion", icon: "💡", title: "运营建议" }
    };
    const sections = parseReportSections(content);
    return sections.map(sec => {
      const cfg = secMap[sec.key] || secMap.a;
      return `
        <div class="report-section ${cfg.cls}">
          <div class="sec-title"><span class="sec-icon">${cfg.icon}</span>${sec.title || cfg.title}</div>
          ${formatReportBody(sec.body)}
        </div>
      `;
    }).join("");
  };

  const extractReportSummary = (content) => {
    const sections = parseReportSections(content);
    // 优先取核心指标概览正文的第一句
    const overview = sections.find(s => s.key === "a");
    if (overview && overview.body) {
      const firstLine = overview.body.split(/\n+/).map(l => l.trim()).filter(l => l)[0];
      if (firstLine) return firstLine;
    }
    const firstBody = sections.map(s => s.body).find(b => b && b.trim());
    if (firstBody) {
      const firstLine = firstBody.split(/\n+/).map(l => l.trim()).filter(l => l)[0];
      if (firstLine) return firstLine;
    }
    return content.substring(0, 80).replace(/\n/g, " ") + (content.length > 80 ? "…" : "");
  };

  const renderReport = (latest, history) => {
    const dateEl = document.getElementById("report-date");
    const summaryEl = document.getElementById("report-summary");
    const hlEl = document.getElementById("report-highlights");
    const tlEl = document.getElementById("report-timeline");
    if (!dateEl) return;

    // 空状态：显示提示
    if (!latest || !latest.content) {
      dateEl.textContent = "--";
      summaryEl.innerHTML = `
        <div class="report-section">
          <div class="sec-title"><span class="sec-icon">⏳</span>等待生成</div>
          <p>晨报尚未生成，可点击右下角 AI 助手或通过 POST /api/report/generate 手动触发。</p>
        </div>
      `;
      if (hlEl) hlEl.innerHTML = `<span class="anomaly-tag">⏳ 等待生成</span>`;
      if (tlEl) tlEl.innerHTML = "";
      return;
    }

    dateEl.innerHTML = `📅 ${latest.date}`;
    summaryEl.innerHTML = buildReportHtml(latest.content);

    let anomalies = latest.anomalies || [];
    if (typeof anomalies === "string") {
      anomalies = anomalies.split(/[，,]/).map(a => a.trim()).filter(a => a);
    }
    hlEl.innerHTML = anomalies.length
      ? anomalies.map(a => {
          const isUp = a.includes("上升");
          const isDown = a.includes("下降");
          const cls = isUp ? "up" : isDown ? "down" : "";
          const icon = isUp ? "📈" : isDown ? "📉" : "⚠️";
          return `<span class="anomaly-tag ${cls}">${icon} ${a}</span>`;
        }).join("")
      : `<span class="anomaly-tag ok">✓ 各指标波动正常</span>`;

    if (tlEl && history) {
      tlEl.innerHTML = history.map((r, idx) => `
        <li data-idx="${idx}">
          <div class="tl-date">${r.date}</div>
          <div class="tl-summary">${extractReportSummary(r.content)}</div>
          <div class="tl-expand">展开全文 ↓</div>
          <div class="tl-detail">${buildReportHtml(r.content)}</div>
        </li>
      `).join("");
    }
  };

  const getCategory = () => {
    const sel = document.getElementById("trend-category");
    const val = sel ? sel.value : "全站";
    return API.CATEGORY_MAP[val] || val;
  };

  const initTrendCategory = () => {
    const sel = document.getElementById("trend-category");
    if (!sel) return;
    sel.innerHTML = (API.CATEGORIES || ["全站"]).map(c => `<option value="${c}">${c}</option>`).join("");
    sel.addEventListener("change", async () => {
      try {
        const data = await API.get(`/api/trend/active?days=7&category=${API.CATEGORY_MAP[sel.value] || sel.value}`);
        Charts.renderTrend(data);
      } catch (err) {
        console.error("Trend reload failed:", err);
      }
    });
  };

  const initTopToggle = () => {
    const toggle = document.getElementById("top-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-metric]");
      if (!btn) return;
      topMetric = btn.dataset.metric;
      toggle.querySelectorAll("button").forEach(b => b.classList.toggle("active", b === btn));
      if (topDataCache) Charts.renderTopProducts(topDataCache, topMetric);
    });
  };

  const initRecommend = () => {
    const input = document.getElementById("rec-user-input");
    const btn = document.getElementById("rec-refresh");
    if (!input || !btn) return;

    const refreshRec = async () => {
      const userId = input.value.trim();
      if (!userId) return;
      try {
        const data = await API.get(`/api/recommend?user_id=${userId}`);
        if (data && data.items) {
          Charts.renderRecommend(data);
        }
      } catch (err) {
        console.error("Recommend load failed:", err);
      }
    };

    btn.addEventListener("click", refreshRec);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") refreshRec();
    });
  };

  const moduleNames = {
    "01": "日活跃用户趋势",
    "02": "商品热度 Top10",
    "03": "转化漏斗",
    "04": "RFM 用户分布",
    "05": "AI 每日晨报",
    "06": "个性化推荐",
    "07": "历史报告"
  };

  const cloneWithFunctions = (obj) => {
    if (obj === null || typeof obj !== "object") return obj;
    if (typeof obj === "function") return obj;
    
    const clone = Array.isArray(obj) ? [] : {};
    for (const key in obj) {
      if (obj.hasOwnProperty(key)) {
        clone[key] = cloneWithFunctions(obj[key]);
      }
    }
    return clone;
  };

  const scaleChartOption = (option) => {
    const scaled = cloneWithFunctions(option);
    
    const scaleNum = (num) => Math.round(num * 1.5);
    
    const scaleFont = (obj, prop) => {
      if (obj && obj[prop] && typeof obj[prop] === "number") {
        obj[prop] = scaleNum(obj[prop]);
      }
    };
    
    const scaleGrid = (grid) => {
      if (!grid) return;
      ["top", "right", "bottom", "left"].forEach(key => {
        if (typeof grid[key] === "number") {
          grid[key] = scaleNum(grid[key]);
        }
      });
    };

    if (scaled.legend) {
      scaleFont(scaled.legend.textStyle, "fontSize");
      if (typeof scaled.legend.top === "number") scaled.legend.top = scaleNum(scaled.legend.top);
    }

    if (scaled.grid) {
      scaleGrid(scaled.grid);
    }

    if (scaled.xAxis) {
      if (Array.isArray(scaled.xAxis)) {
        scaled.xAxis.forEach(axis => {
          scaleFont(axis.axisLabel, "fontSize");
          scaleFont(axis.axisLine?.lineStyle, "width");
        });
      } else {
        scaleFont(scaled.xAxis.axisLabel, "fontSize");
        scaleFont(scaled.xAxis.axisLine?.lineStyle, "width");
      }
    }

    if (scaled.yAxis) {
      if (Array.isArray(scaled.yAxis)) {
        scaled.yAxis.forEach(axis => {
          scaleFont(axis.axisLabel, "fontSize");
          scaleFont(axis.splitLine?.lineStyle, "width");
        });
      } else {
        scaleFont(scaled.yAxis.axisLabel, "fontSize");
        scaleFont(scaled.yAxis.splitLine?.lineStyle, "width");
      }
    }

    if (scaled.tooltip) {
      scaleFont(scaled.tooltip.textStyle, "fontSize");
    }

    if (scaled.series) {
      scaled.series.forEach(series => {
        scaleFont(series.lineStyle, "width");
        scaleFont(series.itemStyle, "borderWidth");
        
        if (series.label) {
          scaleFont(series.label, "fontSize");
        }
        if (series.labelLine) {
          scaleFont(series.labelLine, "length");
          scaleFont(series.labelLine, "length2");
          scaleFont(series.labelLine.lineStyle, "width");
        }
        if (series.gap) {
          series.gap = scaleNum(series.gap);
        }
        if (typeof series.top === "number") series.top = scaleNum(series.top);
        if (typeof series.bottom === "number") series.bottom = scaleNum(series.bottom);
        if (series.barWidth && typeof series.barWidth === "number") {
          series.barWidth = scaleNum(series.barWidth);
        }
      });
    }

    return scaled;
  };

  const initBottomNav = () => {
    const modal = document.getElementById("module-modal");
    const modalTitle = document.getElementById("modal-title");
    const modalBody = document.getElementById("modal-body");
    const modalClose = document.getElementById("modal-close");
    const menuBtn = document.getElementById("nav-menu-btn");
    const bottomNav = document.querySelector(".bottom-nav");
    const navBtns = document.querySelectorAll(".nav-num-btn");

    const closeModal = () => {
      modal.classList.remove("open");
      modalBody.innerHTML = "";
      navBtns.forEach(btn => btn.classList.remove("active"));
    };

    modalClose.addEventListener("click", closeModal);

    menuBtn.addEventListener("click", () => {
      menuBtn.classList.toggle("active");
      bottomNav.classList.toggle("active");
    });

    navBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const moduleId = btn.dataset.module;
        const moduleName = moduleNames[moduleId];

        navBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        modalTitle.textContent = `${moduleId} ${moduleName}`;
        modalBody.innerHTML = "";

        const chartIds = {
          "01": "chart-trend",
          "02": "chart-top",
          "03": "chart-funnel",
          "04": "chart-rfm"
        };

        if (chartIds[moduleId]) {
          modalBody.innerHTML = `<div id="modal-chart" class="chart"></div>`;
          setTimeout(() => {
            const fsChart = echarts.init(document.getElementById("modal-chart"));
            const originalChart = Charts._getInstance(chartIds[moduleId]);
            if (originalChart) {
              const originalOption = originalChart.getOption();
              const scaledOption = scaleChartOption(originalOption);
              fsChart.setOption(scaledOption);
            }
            modal.classList.add("open");

            const resizeObserver = new ResizeObserver(() => fsChart.resize());
            resizeObserver.observe(modalBody);

            const cleanup = () => {
              resizeObserver.disconnect();
              fsChart.dispose();
              modalClose.removeEventListener("click", cleanup);
            };
            modalClose.addEventListener("click", cleanup);
          }, 100);
        } else {
          const moduleEl = document.getElementById(`module-${moduleId}`);
          if (moduleEl) {
            const clone = moduleEl.cloneNode(true);
            clone.style.width = "100%";
            clone.style.height = "100%";
            clone.style.border = "none";
            modalBody.appendChild(clone);
            modal.classList.add("open");
          }
        }
      });
    });

    // 历史报告时间线：点击展开/收起（含模态框克隆节点）
    document.addEventListener("click", (e) => {
      const li = e.target.closest("#report-timeline li");
      if (!li) return;
      const expanded = li.classList.toggle("expanded");
      const expandEl = li.querySelector(".tl-expand");
      if (expandEl) expandEl.textContent = expanded ? "收起全文 ↑" : "展开全文 ↓";
    });
  };

  const initRefresh = () => {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => loadData(), CONFIG.REFRESH_INTERVAL);
  };

  const init = () => {
    updateClock();
    setInterval(updateClock, 1000);

    initTrendCategory();
    initTopToggle();
    initRecommend();
    initBottomNav();

    loadData();
    initRefresh();

    window.addEventListener("resize", () => Charts.resize());
  };

  return { init };
})();

document.addEventListener("DOMContentLoaded", () => {
  Main.init();
});