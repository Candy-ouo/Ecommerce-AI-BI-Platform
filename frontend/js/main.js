const Main = (() => {
  let refreshTimer = null;
  let topDataCache = null;        // 缓存商品热度数据，供指标切换复用
  let topMetric = "pv";
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

  const loadData = async () => {
    updateStatus(true);
    try {
      const [kpiData, trendData, topData, funnelData, rfmData, reportLatest, reportHistory, recommendData] = await Promise.all([
        API.get("/api/kpi/cards"),
        API.get(`/api/trend/active?days=7&category=${getCategory()}`),
        API.get("/api/top/items?limit=10"),
        API.get("/api/funnel"),
        API.get("/api/rfm/dist"),
        API.get("/api/report/latest"),
        API.get("/api/report/history?days=7"),
        API.get("/api/recommend?user_id=98047837")
      ]);

      Charts.renderKPI(kpiData);
      Charts.renderTrend(trendData);
      topDataCache = topData;
      Charts.renderTopProducts(topDataCache, topMetric);
      Charts.renderFunnel(funnelData);
      Charts.renderRFM(rfmData);
      renderReport(reportLatest, reportHistory);
      Charts.renderRecommend(recommendData);
    } catch (err) {
      console.error("Data load failed:", err);
      updateStatus(false);
    }
  };

  // F3.8 晨报渲染：对齐 {date, content, anomalies}
  const renderReport = (latest, history) => {
    const dateEl = document.getElementById("report-date");
    const summaryEl = document.getElementById("report-summary");
    const hlEl = document.getElementById("report-highlights");
    const tlEl = document.getElementById("report-timeline");
    if (!dateEl || !latest) return;

    dateEl.textContent = latest.date;
    summaryEl.textContent = latest.content;

    const anomalies = latest.anomalies || [];
    hlEl.innerHTML = anomalies.length
      ? anomalies.map(a => `<span class="anomaly-tag">⚠ ${a}</span>`).join("")
      : `<span class="anomaly-tag ok">✓ 无异常</span>`;

    if (tlEl && history) {
      tlEl.innerHTML = history.map(r => `
        <li>
          <span class="tl-date">${r.date}</span>${r.content}
        </li>
      `).join("");
    }
  };

  // F3.2 类目下钻：填充下拉 + 切换重新拉取趋势
  const getCategory = () => {
    const sel = document.getElementById("trend-category");
    return sel ? sel.value : "全站";
  };

  const initTrendCategory = () => {
    const sel = document.getElementById("trend-category");
    if (!sel) return;
    sel.innerHTML = (API.CATEGORIES || ["全站"]).map(c => `<option value="${c}">${c}</option>`).join("");
    sel.addEventListener("change", async () => {
      try {
        const data = await API.get(`/api/trend/active?days=7&category=${sel.value}`);
        Charts.renderTrend(data);
      } catch (err) {
        console.error("Trend reload failed:", err);
      }
    });
  };

  // F3.3 热度指标切换：PV / 购买
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

  // F3.6 个性化推荐：输入用户ID后刷新推荐列表
  const initRecommend = () => {
    const input = document.getElementById("rec-user-input");
    const btn = document.getElementById("rec-refresh");
    if (!input || !btn) return;

    const refreshRec = async () => {
      const userId = input.value.trim();
      if (!userId) return;
      try {
        const data = await API.get(`/api/recommend?user_id=${userId}`);
        Charts.renderRecommend(data);
      } catch (err) {
        console.error("Recommend load failed:", err);
      }
    };

    btn.addEventListener("click", refreshRec);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") refreshRec();
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

    loadData();
    initRefresh();

    window.addEventListener("resize", () => Charts.resize());
  };

  return { init };
})();

document.addEventListener("DOMContentLoaded", () => {
  Main.init();
});
