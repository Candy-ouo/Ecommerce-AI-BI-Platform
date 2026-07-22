// config.js —— 全局配置
// 等 C 的后端地址确定后，改 API_BASE_URL；接口就绪后把 USE_MOCK 改为 false 即可切真数据
const CONFIG = {
  API_BASE_URL: "http://localhost:5000", // C 的 Flask 后端地址（联调时确认）
  REFRESH_INTERVAL: 30000,               // 自动刷新间隔(ms)，文档要求 30s
  USE_MOCK: false,                       // C 接口已就绪，走真实 API 数据
  THEME: {
    color: ["#4f8cff", "#36d1b7", "#ffb454", "#ff5c7c", "#9b6cff", "#3dd6e0", "#f6c445", "#7ed957"],
    textColor: "#e6ecff",
    axisLine: "#243056",
    splitLine: "rgba(36,48,86,0.5)"
  }
};
