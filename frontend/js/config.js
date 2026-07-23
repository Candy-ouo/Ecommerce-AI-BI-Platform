// config.js —— 全局配置
// file:// 协议（直接双击打开 HTML）时自动指向后端，http:// 时走相对路径
const CONFIG = {
  API_BASE_URL: (window.location.protocol === "file:")
    ? "http://localhost:5000"
    : "",
  REFRESH_INTERVAL: 120000,
  THEME: {
    color: ["#4f8cff", "#36d1b7", "#ffb454", "#ff5c7c", "#9b6cff", "#3dd6e0", "#f6c445", "#7ed957"],
    textColor: "#e6ecff",
    axisLine: "#243056",
    splitLine: "rgba(36,48,86,0.5)"
  }
};
