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

  const renderTrend = (data) => {
    const chart = initChart("chart-trend");
    if (!chart || !data) return;

    const option = {
      backgroundColor: "transparent",
      grid: { top: 30, right: 70, bottom: 45, left: 65 },
      tooltip: { trigger: "axis", backgroundColor: "#1a2440", borderColor: "#243056", textStyle: { fontSize: 12 } },
      legend: { data: ["DAU", "PV", "订单量"], textStyle: { color: theme.textColor, fontSize: 11 }, top: 2 },
      xAxis: {
        type: "category",
        data: data.dates,
        axisLine: { lineStyle: { color: theme.axisLine, width: 1.5 } },
        axisLabel: { color: theme.textColor, fontSize: 10, rotate: 30 }
      },
      yAxis: [
        { type: "value", splitLine: { lineStyle: { color: theme.splitLine } }, axisLabel: { color: theme.textColor, fontSize: 10, margin: 10 } },
        { type: "value", splitLine: { show: false }, axisLabel: { color: theme.textColor, fontSize: 10, margin: 10 } }
      ],
      series: [
        { name: "DAU", type: "line", smooth: true, data: data.dau, itemStyle: { color: theme.color[0] }, lineStyle: { width: 2 }, symbolSize: 5, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: theme.color[0] + "20" }, { offset: 1, color: theme.color[0] + "05" }]) } },
        { name: "PV", type: "line", smooth: true, data: data.pv, itemStyle: { color: theme.color[1] }, lineStyle: { width: 2 }, yAxisIndex: 1, symbolSize: 5, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: theme.color[1] + "20" }, { offset: 1, color: theme.color[1] + "05" }]) } },
        { name: "订单量", type: "line", smooth: true, data: data.orders, itemStyle: { color: theme.color[2] }, lineStyle: { width: 2 }, symbolSize: 5, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: theme.color[2] + "20" }, { offset: 1, color: theme.color[2] + "05" }]) } }
      ]
    };
    chart.setOption(option);
  };

  const renderTopProducts = (data, metric = "pv") => {
    const chart = initChart("chart-top");
    if (!chart || !data || !data.items) return;

    const metricLabels = { pv: "PV 热度", buy: "购买热度", fav: "收藏热度" };
    const sorted = [...data.items].sort((a, b) => b[metric] - a[metric]).slice(0, 5);
    const display = sorted.slice().reverse();
    const names = display.map(d => d.name || `商品 ${d.item_id}`);
    const values = display.map(d => d[metric]);
    const max = Math.max(...values, 1);

    // 统一紫-蓝渐变，Top1 最深，Top5 最浅
    const rankColors = [
      ["#5b3dff", "#7f6cff"], // 5
      ["#4f48ff", "#6b85ff"], // 4
      ["#3f6aff", "#5ba0ff"], // 3
      ["#2f8aff", "#4fb8ff"], // 2
      ["#1faaff", "#4fd4ff"]  // 1
    ];

    const option = {
      backgroundColor: "transparent",
      grid: { top: 15, right: 60, bottom: 20, left: 110 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "#1a2440",
        borderColor: "#243056",
        textStyle: { fontSize: 12 },
        formatter: (params) => {
          const p = params[0];
          const raw = display[p.dataIndex];
          return `
            <div style="font-weight:bold;margin-bottom:4px;">${p.name}</div>
            <div>PV：${formatNum(raw.pv)}</div>
            <div>收藏：${formatNum(raw.fav)}</div>
            <div>购买：${formatNum(raw.buy)}</div>
          `;
        }
      },
      xAxis: {
        type: "value",
        splitLine: { lineStyle: { color: theme.splitLine } },
        axisLabel: { show: false }
      },
      yAxis: {
        type: "category",
        data: names,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.textColor,
          fontSize: 11,
          align: "right",
          margin: 12,
          formatter: (name) => name.length > 7 ? name.substring(0, 7) + "…" : name
        }
      },
      series: [{
        type: "bar",
        data: values.map((v, i) => ({
          value: v,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: rankColors[i][0] },
              { offset: 1, color: rankColors[i][1] }
            ]),
            borderRadius: [0, 4, 4, 0],
            shadowColor: rankColors[i][0] + "40",
            shadowBlur: 8
          }
        })),
        barWidth: "50%",
        barGap: "10%",
        label: {
          show: true,
          position: "insideLeft",
          offset: [8, 0],
          color: "#fff",
          fontSize: 11,
          fontWeight: "bold",
          formatter: (p) => {
            const rank = 5 - p.dataIndex;
            return `${rank}`;
          }
        },
        // 背景条
        showBackground: true,
        backgroundStyle: {
          color: "rgba(255,255,255,0.03)",
          borderRadius: [0, 4, 4, 0]
        },
        // 数值标签放右侧
        markPoint: {
          symbol: "rect",
          symbolSize: [1, 1],
          label: {
            show: true,
            position: "right",
            distance: 6,
            color: theme.textColor,
            fontSize: 10,
            formatter: (p) => formatNum(p.value)
          },
          data: values.map((v, i) => ({ coord: [v, i], value: v }))
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 14,
            shadowColor: "rgba(79,140,255,0.55)"
          }
        }
      }]
    };
    chart.setOption(option, true);
  };

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

    // 计算相邻环节转化率
    const stepRates = stages.map((s, i) => {
      if (i >= stages.length - 1) return null;
      return s.value ? ((stages[i + 1].value / s.value) * 100).toFixed(1) : "0.0";
    });

    // 统一蓝色系：从上到下由深到浅
    const blues = [
      ["#2b6aff", "#5b9dff"],
      ["#4a85ff", "#79b0ff"],
      ["#699eff", "#96c4ff"],
      ["#88b6ff", "#b4d8ff"]
    ];

    const option = {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        backgroundColor: "#1a2440",
        borderColor: "#243056",
        textStyle: { fontSize: 12 },
        formatter: (p) => {
          const idx = stages.findIndex(s => s.name === p.name);
          const share = ((p.value / max) * 100).toFixed(1);
          let html = `<div style="font-weight:bold;margin-bottom:4px;">${p.name}</div>`;
          html += `用户数：${formatNum(p.value)}<br/>`;
          html += `占首环节：${share}%`;
          if (idx < stages.length - 1) {
            html += `<br/>→ 下一环节：${stepRates[idx]}%`;
          }
          return html;
        }
      },
      series: [{
        type: "funnel",
        left: "10%",
        top: 25,
        bottom: 25,
        width: "55%",
        min: 0,
        max: max,
        minSize: "12%",
        maxSize: "88%",
        sort: "descending",
        gap: 3,
        label: {
          show: true,
          position: "inside",
          color: "#fff",
          fontSize: 12,
          fontWeight: "bold",
          lineHeight: 17,
          formatter: (p) => {
            const idx = stages.findIndex(s => s.name === p.name);
            const rateText = idx < stages.length - 1 ? `\n→ ${stepRates[idx]}%` : "";
            return `${p.name}\n${formatNum(p.value)}${rateText}`;
          }
        },
        labelLine: { show: false },
        itemStyle: {
          borderColor: "#131a2e",
          borderWidth: 2,
          borderRadius: 6
        },
        emphasis: {
          label: { fontSize: 13 },
          itemStyle: { shadowBlur: 12, shadowColor: "rgba(79,140,255,0.45)" }
        },
        data: stages.map((s, i) => ({
          value: s.value,
          name: s.name,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: blues[i][0] },
              { offset: 1, color: blues[i][1] }
            ])
          }
        }))
      }],
      // 右侧转化率指示器
      graphic: stages.slice(0, -1).map((s, i) => {
        const next = stages[i + 1];
        const rate = stepRates[i];
        return {
          type: "group",
          left: "72%",
          top: `${18 + i * 20}%`,
          children: [
            {
              type: "text",
              style: {
                text: `${s.name} → ${next.name}`,
                fill: theme.textColor,
                fontSize: 10,
                opacity: 0.75
              }
            },
            {
              type: "text",
              top: 13,
              style: {
                text: `${rate}%`,
                fill: theme.color[0],
                fontSize: 13,
                fontWeight: "bold"
              }
            }
          ]
        };
      })
    };
    chart.setOption(option, true);
  };

  const renderRFM = (data) => {
    const chart = initChart("chart-rfm");
    if (!chart || !data) return;

    const option = {
      backgroundColor: "transparent",
      tooltip: { trigger: "item", backgroundColor: "#1a2440", borderColor: "#243056", formatter: "{b}: {c} ({d}%)", textStyle: { fontSize: 12 } },
      legend: { show: false },
      series: [{
        type: "pie",
        radius: ["35%", "70%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 5, borderColor: "#131a2e", borderWidth: 1.5 },
        label: {
          show: true,
          position: "outside",
          color: theme.textColor,
          fontSize: 10,
          formatter: "{b}: {d}%"
        },
        emphasis: { label: { show: true, fontSize: 11, fontWeight: "bold", color: theme.textColor } },
        labelLine: {
          show: true,
          length: 12,
          length2: 18,
          lineStyle: {
            color: theme.textColor,
            width: 1
          }
        },
        data: data.labels.map((label, i) => ({
          value: data.counts[i],
          name: label,
          itemStyle: { color: theme.color[i % theme.color.length] }
        }))
      }]
    };
    chart.setOption(option);
  };

  const renderRecommend = (data) => {
    const container = document.getElementById("recommend-list");
    if (!container || !data || !data.items) return;

    const userIdEl = document.getElementById("recommend-user");
    const typeTagEl = document.getElementById("recommend-type-tag");
    if (userIdEl) userIdEl.textContent = data.user_id || "--";
    if (typeTagEl) {
      typeTagEl.textContent = data.type === "personalized" ? "个性化推荐" : "热销推荐";
      typeTagEl.className = `rec-type-tag ${data.type || "hot"}`;
    }

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

  const _getInstance = (id) => instances[id];

  return { renderKPI, renderTrend, renderTopProducts, renderFunnel, renderRFM, renderRecommend, resize, _getInstance };
})();