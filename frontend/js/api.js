const API = (() => {
  const { API_BASE_URL } = CONFIG;
  const FETCH_TIMEOUT = 60000;  // 60s 超时，Hive 查询首次执行较慢

  const request = async (path, options = {}) => {
    const url = `${API_BASE_URL}${path}`;
    const defaults = {
      headers: { "Content-Type": "application/json" }
    };
    const merged = { ...defaults, ...options };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT);
    try {
      const res = await fetch(url, { ...merged, signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.code !== 0) throw new Error(data.message || "API error");
      return data.data;
    } catch (err) {
      clearTimeout(timeoutId);
      throw err;
    }
  };

  const CATEGORIES = ["全站", "数码", "服饰", "家居", "美妆", "食品"];
  const CATEGORY_MAP = {
    "全站": "all",
    "数码": "4245",
    "服饰": "4246",
    "家居": "4247",
    "美妆": "4248",
    "食品": "4249"
  };

  const get = async (path) => {
    return request(path);
  };

  const post = async (path, body) => {
    return request(path, { method: "POST", body: JSON.stringify(body) });
  };

  return { get, post, CATEGORIES, CATEGORY_MAP };
})();
