// Live totals: refresh every 10 seconds on any page that shows [data-stat].
const nodes = document.querySelectorAll("[data-stat]");
if (nodes.length) {
  const refresh = async () => {
    try {
      const s = await (await fetch("/api/stats")).json();
      nodes.forEach(n => { n.textContent = s[n.dataset.stat]; });
    } catch (_) { /* offline: keep the last numbers */ }
  };
  setInterval(refresh, 10000);
}
