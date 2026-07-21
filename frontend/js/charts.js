const Charts = (() => {
  const theme = CONFIG.THEME;
  let instances = {};

  const initChart = (id) => {
    const dom = document.getElementById(id);
    if (!dom) return null;
    if (instances[id]) {
      instances[id].dispose();
    }
    const chart = echarts.init(dom);
    instances[id] = chart;
    return chart;
  };

  const formatNum = (num) => {
    if (num >= 10000) return (num / 10000).toFixed(1) + "万";
    return num.toLocaleString();
  };

  // F3.1 KPI 指标卡：使用后端返回的 *_change 环比字段；转化率按比例展示
  const renderKPI = (data) => {
    const container = document.getElementById("kpi-cards");
    if (!container || !data) return;

    const items = [
      { label: "日活跃用户 DAU", value: data.dau, suffix: "", change: data.dau_change },
      { label: "订单量", value: data.orders, suffix: "", change: data.orders_change },
      { label: "转化率", value: data.conversion_rate, suffix: "%", ratio: true, change: data.conversion_change },
      { label: "人均 PV", value: data.avg_pv, suffix: "", change: data.avg_pv_change }
    ];

    container.innerHTML = items.map((item, idx) => {
      const displayVal = item.ratio ? (item.value * 100).toFixed(2) : formatNum(item.value);
      const up = item.change >= 0;
      const changeTxt = (item.change >= 0 ? "+" : "") + (item.change * 100).toFixed(1) + "%";
      return `
        <div class="kpi-card">
          <div class="label">${item.label}</div>
          <div class="value" style="color: ${theme.color[idx]}">${displayVal}${item.suffix}</div>
          <div class="change ${up ? "up" : "down"}">${changeTxt} 环比</div>
        </div>`;
    }).join("");
  };

  // F3.2 活跃趋势：DAU / PV / 订单量三线
  const renderTrend = (data) => {
    const chart = initChart("chart-trend");
    if (!chart || !data) return;

    const option = {
      backgroundColor: "transparent",
      grid: { top: 36, right: 20, bottom: 30, left: 55 },
      tooltip: { trigger: "axis", backgroundColor: "#1a2440", borderColor: "#243056" },
      legend: { data: ["DAU", "PV", "订单量"], textStyle: { color: theme.textColor }, top: 0 },
      xAxis: {
        type: "category",
        data: data.dates,
        axisLine: { lineStyle: { color: theme.axisLine } },
        axisLabel: { color: theme.textColor }
      },
      yAxis: [
        { type: "value", splitLine: { lineStyle: { color: theme.splitLine } }, axisLabel: { color: theme.textColor } },
        { type: "value", splitLine: { show: false }, axisLabel: { color: theme.textColor } }
      ],
      series: [
        { name: "DAU", type: "line", smooth: true, data: data.dau, itemStyle: { color: theme.color[0] }, lineStyle: { width: 2 } },
        { name: "PV", type: "line", smooth: true, data: data.pv, itemStyle: { color: theme.color[1] }, lineStyle: { width: 2 }, yAxisIndex: 1 },
        { name: "订单量", type: "line", smooth: true, data: data.orders, itemStyle: { color: theme.color[2] }, lineStyle: { width: 2 } }
      ]
    };
    chart.setOption(option);
  };

  // F3.3 商品热度 Top10：支持 metric = "pv" | "buy"
  const renderTopProducts = (data, metric = "pv") => {
    const chart = initChart("chart-top");
    if (!chart || !data || !data.items) return;

    const sorted = [...data.items].sort((a, b) => b[metric] - a[metric]).slice(0, 10);
    const names = sorted.map(d => d.name || `商品 ${d.item_id}`);
    const values = sorted.map(d => d[metric]);

    const option = {
      backgroundColor: "transparent",
      grid: { top: 20, right: 60, bottom: 30, left: 90 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "#1a2440", borderColor: "#243056" },
      xAxis: { type: "value", splitLine: { lineStyle: { color: theme.splitLine } }, axisLabel: { color: theme.textColor } },
      yAxis: {
        type: "category",
        data: names.slice().reverse(),
        axisLine: { lineStyle: { color: theme.axisLine } },
        axisLabel: { color: theme.textColor }
      },
      series: [{
        type: "bar",
        data: values.slice().reverse().map((v, i) => ({
          value: v,
          itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            [0, theme.color[i % theme.color.length]],
            [1, theme.color[(i + 1) % theme.color.length]]
          ]) }
        })),
        barWidth: "55%"
      }]
    };
    chart.setOption(option);
  };

  // F3.4 转化漏斗：浏览 → 收藏 → 加购 → 购买
  const renderFunnel = (data) => {
    const chart = initChart("chart-funnel");
    if (!chart || !data) return;

    const stages = [
      { name: "浏览", value: data.pv },
      { name: "收藏", value: data.fav },
      { name: "加购", value: data.cart },
      { name: "购买", value: data.buy }
    ];
    const max = stages[0].value;

    const option = {
      backgroundColor: "transparent",
      tooltip: { trigger: "item", backgroundColor: "#1a2440", borderColor: "#243056", formatter: (p) => `${p.name}: ${formatNum(p.value)} (${((p.value / max) * 100).toFixed(1)}%)` },
      series: [{
        type: "funnel",
        left: "8%",
        top: 16,
        bottom: 16,
        width: "84%",
        min: 0,
        max: max,
        minSize: "20%",
        maxSize: "100%",
        sort: "descending",
        gap: 3,
        label: { show: true, position: "inside", color: "#fff", formatter: "{b}\n{c}" },
        labelLine: { show: false },
        itemStyle: { borderColor: "#1a2440", borderWidth: 1 },
        emphasis: { label: { fontSize: 14 } },
        data: stages.map((s, i) => ({
          value: s.value,
          name: s.name,
          itemStyle: { color: theme.color[i % theme.color.length] }
        }))
      }]
    };
    chart.setOption(option);
  };

  // F3.5 RFM 分布饼图：8 类用户分层
  const renderRFM = (data) => {
    const chart = initChart("chart-rfm");
    if (!chart || !data) return;

    const option = {
      backgroundColor: "transparent",
      tooltip: { trigger: "item", backgroundColor: "#1a2440", borderColor: "#243056", formatter: "{b}: {c} ({d}%)" },
      legend: { orient: "vertical", right: 10, top: "center", textStyle: { color: theme.textColor, fontSize: 11 } },
      series: [{
        type: "pie",
        radius: ["40%", "70%"],
        center: ["35%", "50%"],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 6, borderColor: "#131a2e", borderWidth: 2 },
        label: { show: false, position: "center" },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: "bold", color: theme.textColor } },
        labelLine: { show: false },
        data: data.labels.map((label, i) => ({
          value: data.counts[i],
          name: label,
          itemStyle: { color: theme.color[i % theme.color.length] }
        }))
      }]
    };
    chart.setOption(option);
  };

  // F3.6 个性化推荐列表：展示推荐商品、分数、推荐理由
  const renderRecommend = (data) => {
    const container = document.getElementById("recommend-list");
    if (!container || !data || !data.items) return;

    const userIdEl = document.getElementById("recommend-user");
    if (userIdEl) userIdEl.textContent = data.user_id || "--";

    container.innerHTML = data.items.map((item, idx) => `
      <div class="rec-item">
        <div class="rec-rank">${idx + 1}</div>
        <div class="rec-info">
          <div class="rec-name">${item.name || `商品 ${item.item_id}`}</div>
          <div class="rec-reason">${item.reason || ""}</div>
        </div>
        <div class="rec-score">
          <div class="score-bar">
            <div class="score-fill" style="width: ${(item.score * 100).toFixed(0)}%; background: ${theme.color[idx % theme.color.length]}"></div>
          </div>
          <span class="score-num">${(item.score * 100).toFixed(0)}%</span>
        </div>
      </div>
    `).join("");
  };

  const resize = () => {
    Object.values(instances).forEach(chart => chart.resize());
  };

  return { renderKPI, renderTrend, renderTopProducts, renderFunnel, renderRFM, renderRecommend, resize };
})();
