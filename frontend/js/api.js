const API = (() => {
  const { API_BASE_URL, USE_MOCK } = CONFIG;

  const request = async (path, options = {}) => {
    const url = `${API_BASE_URL}${path}`;
    const defaults = {
      headers: { "Content-Type": "application/json" },
      credentials: "include"
    };
    const merged = { ...defaults, ...options };

    try {
      const res = await fetch(url, merged);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.code !== 0) throw new Error(data.message || "API error");
      return data.data;
    } catch (err) {
      console.error(`API request failed [${path}]:`, err);
      throw err;
    }
  };

  // 类目列表（供趋势图下钻使用）
  const CATEGORIES = ["全站", "数码", "服饰", "家居", "美妆", "食品"];

  const mockData = {
    // F3.1 KPI —— 对齐 /api/kpi/cards：{dau, dau_change, orders, conversion_rate, avg_pv}
    kpi: () => ({
      dau: 12345,
      dau_change: -0.03,
      orders: 8900,
      orders_change: 0.061,
      conversion_rate: 0.0382,   // 比例值，前端 ×100 展示
      conversion_change: 0.005,
      avg_pv: 8.5,
      avg_pv_change: 0.024
    }),

    // F3.2 活跃趋势 —— 对齐 /api/trend/active?days=7[&category=xxx]
    trend: (category) => {
      const dates = ["07-14", "07-15", "07-16", "07-17", "07-18", "07-19", "07-20"];
      const scale = category === "全站" ? 1 : (0.25 + Math.random() * 0.5);
      const dau = dates.map(() => Math.round((8000 + Math.random() * 5000) * scale));
      const pv = dau.map(v => Math.round(v * (10 + Math.random() * 4)));
      const orders = dau.map(v => Math.round(v * (0.6 + Math.random() * 0.3)));
      return { dates, dau, pv, orders };
    },

    // F3.3 商品热度 —— 对齐 /api/top/items?limit=10：{items:[{item_id, pv, buy}]}
    topProducts: () => ({
      items: [
        { item_id: 232431562, name: "无线蓝牙耳机", pv: 12580, buy: 420 },
        { item_id: 312051294, name: "智能手表", pv: 9850, buy: 380 },
        { item_id: 290045133, name: "机械键盘", pv: 7620, buy: 290 },
        { item_id: 198772345, name: "游戏鼠标", pv: 6450, buy: 260 },
        { item_id: 256633788, name: "便携音箱", pv: 5380, buy: 210 },
        { item_id: 277891022, name: "USB-C扩展坞", pv: 4250, buy: 175 },
        { item_id: 301245677, name: "无线充电器", pv: 3890, buy: 150 },
        { item_id: 264419900, name: "降噪耳机", pv: 3560, buy: 165 },
        { item_id: 245678311, name: "蓝牙键盘", pv: 2980, buy: 120 },
        { item_id: 288134599, name: "移动电源", pv: 2650, buy: 110 }
      ]
    }),

    // F3.4 转化漏斗 —— 对齐 /api/funnel：{pv, fav, cart, buy}
    funnel: () => ({
      pv: 100000,
      fav: 35000,
      cart: 20000,
      buy: 8000
    }),

    // F3.5 RFM 分布 —— 对齐 /api/rfm/dist：{labels, counts}（9 类，含"浏览型用户"）
    rfm: () => ({
      labels: ["重要价值用户", "重要保持用户", "重要发展用户", "重要挽留用户",
               "一般价值用户", "一般发展用户", "新锐潜力用户", "低价值用户", "浏览型用户"],
      counts: [12500, 8900, 7600, 6200, 15800, 9600, 5500, 4800, 7200]
    }),

    // F3.8 最新晨报 —— 对齐 /api/report/latest：{date, content, anomalies}
    reportLatest: () => ({
      date: "2014-12-18",
      content: "今日 DAU 12,345（环比 -3.0%），全站转化率 3.82%（+0.5pp）。数码品类转化率下降 12%，建议加大促销力度；美妆品类 PV 环比 +18%，表现亮眼。",
      anomalies: ["数码品类转化率下降 12%", "美妆品类 PV 环比 +18%"]
    }),

    // F3.8 历史晨报 —— 对齐 /api/report/history?days=7：[{date, content, anomalies}]
      reportHistory: () => ([
        { date: "2014-12-18", content: "今日 DAU 12,345，转化率 3.82%。数码品类下滑需关注。", anomalies: ["数码品类转化率下降 12%"] },
        { date: "2014-12-17", content: "昨日 DAU 12,730，整体平稳，服饰品类购买热度上升。", anomalies: ["服饰品类购买 +9%"] },
        { date: "2014-12-16", content: "大促预热，PV 创历史新高，加购率提升明显。", anomalies: [] },
        { date: "2014-12-15", content: "DAU 环比 +5%，新用户占比提升。", anomalies: ["新用户占比 +2pp"] },
        { date: "2014-12-14", content: "周末家居品类表现突出，转化率领先。", anomalies: [] }
      ]),

      // F3.6 个性化推荐 —— 对齐 /api/recommend?user_id=xxx：{items:[{item_id, name, score, reason}]}
      recommend: (userId) => ({
        user_id: userId || 98047837,
        items: [
          { item_id: 232431562, name: "无线蓝牙耳机", score: 0.92, reason: "您最近浏览了同类商品，相似用户中 78% 最终购买了此商品" },
          { item_id: 312051294, name: "智能手表", score: 0.85, reason: "基于您的购买历史，推荐同系列智能穿戴产品" },
          { item_id: 290045133, name: "机械键盘", score: 0.78, reason: "该商品与您加购的游戏鼠标搭配购买率达 65%" },
          { item_id: 198772345, name: "游戏鼠标", score: 0.72, reason: "您浏览过此商品，当前有促销优惠活动" },
          { item_id: 256633788, name: "便携音箱", score: 0.65, reason: "根据您的兴趣偏好推荐" }
        ]
      })
    };

  const get = async (path) => {
    if (USE_MOCK) {
      // 趋势图支持类目下钻
      if (path.startsWith("/api/trend/active")) {
        const qs = new URLSearchParams(path.split("?")[1] || "");
        return mockData.trend(qs.get("category") || "全站");
      }
      // 推荐接口支持 user_id 参数
      if (path.startsWith("/api/recommend")) {
        const qs = new URLSearchParams(path.split("?")[1] || "");
        return mockData.recommend(qs.get("user_id"));
      }
      const mockFn = {
        "/api/kpi/cards": mockData.kpi,
        "/api/top/items": mockData.topProducts,
        "/api/funnel": mockData.funnel,
        "/api/rfm/dist": mockData.rfm,
        "/api/report/latest": mockData.reportLatest,
        "/api/report/history": mockData.reportHistory
      }[path.split("?")[0]];
      if (mockFn) return mockFn();
    }
    return request(path);
  };

  const post = async (path, body) => {
    return request(path, { method: "POST", body: JSON.stringify(body) });
  };

  return { get, post, CATEGORIES };
})();
